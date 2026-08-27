import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_development_probe_candidate import _assembled_fixture

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "skills" / "atom-building-machinery" / "scripts" / "atom_controller.py"
COMPOSE = ROOT / "skills" / "experiment-machinery" / "scripts" / "development_probe_compose.py"
ATOM_ID = "composed-candidate"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def invoke(*args: object, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CONTROLLER), *(str(arg) for arg in args)],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture(scope="module")
def assembly_fixture(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, object], str]:
    root = tmp_path_factory.mktemp("atom-real-assembly")
    manifest_path, assembly = _assembled_fixture(root)
    manifest = json.loads(manifest_path.read_text())["atomic_step"]
    verified = subprocess.run(
        [sys.executable, str(COMPOSE), "verify", str(assembly)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert verified.returncode == 0, verified.stderr
    assembly_sha256 = json.loads(verified.stdout)["assembly_sha256"]
    return assembly, manifest, assembly_sha256


def request(manifest: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "atomic_step_id": ATOM_ID,
        "outcome": manifest["outcome"],
        "practical_value": manifest["practical_value"],
        "stopping_condition": manifest["stopping_condition"],
        "allowed_paths": ["src/records", "tests/records"],
        "captured_cases": [
            {
                "case_id": case["id"],
                "source_ref": case["source"],
                "sha256": case["sha256"],
                "kind": case["kind"],
                "expected_outcome": case["expected_outcome"],
            }
            for case in manifest["captured_cases"]
        ],
    }


def stage_receipt(stage: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "stage": stage,
        "status": "completed",
        "exit_code": 0,
        "output": f"{stage}/output",
        "evidence": f"{stage}/evidence.json",
        "evidence_sha256": "0" * 64,
        "result": f"{stage}/result.json",
        "result_sha256": "1" * 64,
        "promotion_applied": False,
    }


def experiment(
    path: Path,
    assembly_fixture: tuple[Path, dict[str, object], str],
    verdict: str = "passed",
) -> None:
    assembly, _, assembly_sha256 = assembly_fixture
    shutil.copytree(assembly, path / "composition" / "assembly", copy_function=shutil.copy2)
    case_verdict = "satisfied" if verdict == "passed" else "not-satisfied"
    final = {
        "schema_version": 1,
        "status": "completed",
        "atomic_step_id": ATOM_ID,
        "assembly_sha256": assembly_sha256,
        "verdict": verdict,
        "cases": [
            {
                "case_id": case_id,
                "verdict": case_verdict,
                "reason": "Captured evidence decides this case.",
                "evidence_pointers": [f"cases/{case_id}/result.json"],
            }
            for case_id in ("works", "refuses")
        ],
        "promotion_applied": False,
    }
    final_path = path / "final-verdict.json"
    write_json(final_path, final)
    final_sha = hashlib.sha256(final_path.read_bytes()).hexdigest()
    write_json(
        path / "development-probe-summary.json",
        {
            "schema_version": 1,
            "status": "completed",
            "atomic_step_id": ATOM_ID,
            "verdict": verdict,
            "final_verdict_sha256": final_sha,
            "stages": [stage_receipt(stage) for stage in ("run-probes", "compose-winners", "final-validation")],
            "promotion_applied": False,
        },
    )


def start(tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]) -> Path:
    request_path = tmp_path / "request.json"
    run = tmp_path / "run"
    write_json(tmp_path / "src" / "records" / "save.py", {"version": "baseline"})
    write_json(tmp_path / "tests" / "records" / "test_save.py", {"version": "baseline"})
    write_json(request_path, request(assembly_fixture[1]))
    result = invoke("start", request_path, run, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["next_skill"] == "prototype-driven-implementation"
    assert state["required_capability"] == "experiment-machinery"
    return run


def read_state(run: Path) -> dict[str, object]:
    result = invoke("status", run)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def evidence(path: Path, case_id: str) -> dict[str, str]:
    write_json(path, {"case_id": case_id, "observed": "expected operator-path result"})
    return {
        "case_id": case_id,
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def promotion_receipt(path: Path, run: Path, state: dict[str, object]) -> None:
    current = state["current_experiment"]
    root = run.parent
    write_json(root / "src" / "records" / "save.py", {"version": "promoted"})
    write_json(root / "tests" / "records" / "test_save.py", {"version": "promoted"})
    surface_path = path.parent / "change-surface.json"
    if not surface_path.exists():
        surfaced = invoke("change-surface", run, surface_path)
        assert surfaced.returncode == 0, surfaced.stderr
    surface_sha256 = hashlib.sha256(surface_path.read_bytes()).hexdigest()
    review_path = path.parent / "final-review.json"
    write_json(
        review_path,
        {
            "schema_version": 1,
            "status": "completed",
            "verdict": "passed",
            "change_surface_sha256": surface_sha256,
            "blocking_findings": [],
        },
    )
    write_json(
        path,
        {
            "schema_version": 1,
            "status": "promoted",
            "atomic_step_id": ATOM_ID,
            "controller": "prototype-driven-implementation",
            "experiment_event_sha256": current["event_sha256"],
            "experiment_assembly_sha256": current["assembly_sha256"],
            "changed_paths": ["src/records/save.py", "tests/records/test_save.py"],
            "change_surface": {
                "path": str(surface_path),
                "sha256": surface_sha256,
            },
            "review": {
                "path": str(review_path),
                "sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
            },
            "evidence": [
                evidence(path.parent / "promotion-evidence" / f"{case_id}.json", case_id)
                for case_id in ("works", "refuses")
            ],
        },
    )


def validation_receipt(path: Path, state: dict[str, object], verdict: str = "satisfied") -> None:
    write_json(
        path,
        {
            "schema_version": 1,
            "status": "completed",
            "atomic_step_id": ATOM_ID,
            "promotion_event_sha256": state["current_promotion"]["event_sha256"],
            "cases": [
                {
                    "case_id": case_id,
                    "verdict": verdict,
                    "reason": "The real operator path produced the expected result.",
                    "evidence": [
                        evidence(path.parent / "real-path" / f"{case_id}.json", case_id)
                    ],
                }
                for case_id in ("works", "refuses")
            ],
        },
    )


def test_complete_journey_authorizes_next_atom(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    result = invoke("record-experiment", run, experiment_path)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["stage"] == "promotion"
    assert state["next_skill"] == "prototype-driven-implementation"
    assert state["required_capability"] == "promotion"

    promotion_path = tmp_path / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    result = invoke("record-promotion", run, promotion_path)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["stage"] == "validation"
    assert state["next_skill"] == "prototype-driven-implementation"
    assert state["required_capability"] == "real-path-validation"

    validation_path = tmp_path / "validation.json"
    validation_receipt(validation_path, state)
    result = invoke("record-validation", run, validation_path)
    assert result.returncode == 0, result.stderr
    completed = json.loads(result.stdout)
    assert completed["stage"] == "complete"
    assert completed["next_skill"] is None
    assert completed["required_capability"] is None

    result = invoke("authorize-next", run)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["authorized"] is True


def test_missing_or_mismatched_promotion_evidence_cannot_advance(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    state = json.loads(invoke("record-experiment", run, experiment_path).stdout)
    promotion_path = tmp_path / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    receipt = json.loads(promotion_path.read_text())

    Path(receipt["evidence"][0]["path"]).unlink()
    missing = invoke("record-promotion", run, promotion_path)
    assert missing.returncode == 2
    assert "evidence is unavailable or linked" in missing.stderr

    promotion_receipt(promotion_path, run, state)
    receipt = json.loads(promotion_path.read_text())
    receipt["evidence"][0]["sha256"] = "0" * 64
    write_json(promotion_path, receipt)
    mismatched = invoke("record-promotion", run, promotion_path)
    assert mismatched.returncode == 2
    assert "evidence has SHA-256" in mismatched.stderr


def test_tampered_case_evidence_blocks_completed_run_resume(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    state = json.loads(invoke("record-experiment", run, experiment_path).stdout)
    promotion_path = tmp_path / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    state = json.loads(invoke("record-promotion", run, promotion_path).stdout)
    validation_path = tmp_path / "validation.json"
    validation_receipt(validation_path, state)
    assert invoke("record-validation", run, validation_path).returncode == 0

    receipt = json.loads(validation_path.read_text())
    Path(receipt["cases"][0]["evidence"][0]["path"]).write_text("changed\n")
    result = invoke("authorize-next", run)
    assert result.returncode == 2
    assert "recorded validation evidence" in result.stderr
    assert "has SHA-256" in result.stderr


def test_tampered_promotion_evidence_blocks_validation_resume(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    state = json.loads(invoke("record-experiment", run, experiment_path).stdout)
    promotion_path = tmp_path / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    assert invoke("record-promotion", run, promotion_path).returncode == 0

    receipt = json.loads(promotion_path.read_text())
    Path(receipt["evidence"][0]["path"]).write_text("changed\n")
    result = invoke("status", run)
    assert result.returncode == 2
    assert "recorded promotion evidence" in result.stderr
    assert "has SHA-256" in result.stderr


def test_refuses_premature_promotion_completion_and_next_atom(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    fake = tmp_path / "fake.json"
    write_json(fake, {})
    promotion = invoke("record-promotion", run, fake)
    validation = invoke("record-validation", run, fake)
    next_atom = invoke("authorize-next", run)
    assert promotion.returncode == validation.returncode == next_atom.returncode == 2
    assert "require 'promotion'" in promotion.stderr
    assert "require 'validation'" in validation.stderr
    assert "finish the reported required_capability" in next_atom.stderr


def test_failed_experiment_is_preserved_and_routes_back_to_experiment(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "failed-experiment"
    experiment(experiment_path, assembly_fixture, "failed")
    result = invoke("record-experiment", run, experiment_path)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["stage"] == "experiment"
    assert state["next_skill"] == "prototype-driven-implementation"
    assert state["required_capability"] == "experiment-machinery"
    assert state["event_count"] == 2


def test_experiment_without_verified_assembly_cannot_advance(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    (experiment_path / "composition" / "assembly").rename(
        experiment_path / "composition" / "removed-assembly"
    )

    result = invoke("record-experiment", run, experiment_path)

    assert result.returncode == 2
    assert "Experiment Machinery refused the recorded assembly" in result.stderr
    assert read_state(run)["stage"] == "experiment"


def test_failed_real_path_routes_back_to_experiment(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    result = invoke("record-experiment", run, experiment_path)
    state = json.loads(result.stdout)
    promotion_path = tmp_path / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    result = invoke("record-promotion", run, promotion_path)
    state = json.loads(result.stdout)
    validation_path = tmp_path / "validation.json"
    validation_receipt(validation_path, state, "not-satisfied")
    result = invoke("record-validation", run, validation_path)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["stage"] == "experiment"
    assert state["next_skill"] == "prototype-driven-implementation"
    assert state["required_capability"] == "experiment-machinery"


def test_tampered_ledger_is_refused(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    ledger = run / "ledger.jsonl"
    ledger.write_text(ledger.read_text().replace(f'"{ATOM_ID}"', '"atom-X"'))
    result = invoke("status", run)
    assert result.returncode == 2
    assert f"require preserved request identity '{ATOM_ID}'" in result.stderr


def test_overwritten_receipt_blocks_completed_run_resume(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    state = json.loads(invoke("record-experiment", run, experiment_path).stdout)
    promotion_path = tmp_path / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    state = json.loads(invoke("record-promotion", run, promotion_path).stdout)
    validation_path = tmp_path / "validation.json"
    validation_receipt(validation_path, state)
    assert invoke("record-validation", run, validation_path).returncode == 0

    validation_path.write_text("{}\n")
    result = invoke("authorize-next", run)
    assert result.returncode == 2
    assert "recorded validation receipt has SHA-256" in result.stderr


def test_replaced_assembly_blocks_promotion_resume(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    assert invoke("record-experiment", run, experiment_path).returncode == 0
    (experiment_path / "composition" / "assembly").rename(
        experiment_path / "composition" / "removed-assembly"
    )

    result = invoke("status", run)

    assert result.returncode == 2
    assert "Experiment Machinery refused the recorded assembly" in result.stderr


def test_change_surface_excludes_unchanged_preexisting_allowed_files(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    write_json(tmp_path / "src" / "records" / "save.py", {"version": "promoted"})
    surface_path = tmp_path / "surface.json"

    result = invoke("change-surface", run, surface_path)

    assert result.returncode == 0, result.stderr
    surface = json.loads(surface_path.read_text())
    assert [item["path"] for item in surface["changes"]] == ["src/records/save.py"]
    assert surface["changes"][0]["kind"] == "changed"


def test_change_surface_includes_permission_only_changes(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    changed = tmp_path / "src" / "records" / "save.py"
    changed.chmod(0o755)
    surface_path = tmp_path / "surface.json"

    result = invoke("change-surface", run, surface_path)

    assert result.returncode == 0, result.stderr
    change = json.loads(surface_path.read_text())["changes"][0]
    assert change["path"] == "src/records/save.py"
    assert change["before_sha256"] == change["after_sha256"]
    assert change["before_mode"] != change["after_mode"]


def test_promotion_refuses_changed_paths_that_differ_from_actual_surface(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    state = json.loads(invoke("record-experiment", run, experiment_path).stdout)
    promotion_path = tmp_path / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    receipt = json.loads(promotion_path.read_text())
    receipt["changed_paths"][1] = "tests/records/invented.py"
    write_json(promotion_path, receipt)

    result = invoke("record-promotion", run, promotion_path)

    assert result.returncode == 2
    assert "changed_paths" in result.stderr
    assert "exact derived change surface" in result.stderr


def test_promotion_requires_present_current_untampered_review(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    state = json.loads(invoke("record-experiment", run, experiment_path).stdout)
    promotion_path = tmp_path / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    receipt = json.loads(promotion_path.read_text())
    review_path = Path(receipt["review"]["path"])

    review_path.unlink()
    missing = invoke("record-promotion", run, promotion_path)
    assert missing.returncode == 2
    assert "review is unavailable or linked" in missing.stderr

    promotion_receipt(promotion_path, run, state)
    receipt = json.loads(promotion_path.read_text())
    review_path = Path(receipt["review"]["path"])
    review = json.loads(review_path.read_text())
    review["change_surface_sha256"] = "0" * 64
    write_json(review_path, review)
    receipt["review"]["sha256"] = hashlib.sha256(review_path.read_bytes()).hexdigest()
    write_json(promotion_path, receipt)
    stale = invoke("record-promotion", run, promotion_path)
    assert stale.returncode == 2
    assert "review change_surface_sha256" in stale.stderr

    promotion_receipt(promotion_path, run, state)
    receipt = json.loads(promotion_path.read_text())
    Path(receipt["review"]["path"]).write_text("tampered\n")
    tampered = invoke("record-promotion", run, promotion_path)
    assert tampered.returncode == 2
    assert "review has SHA-256" in tampered.stderr


def test_tampered_review_blocks_promotion_resume(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    state = json.loads(invoke("record-experiment", run, experiment_path).stdout)
    promotion_path = tmp_path / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    assert invoke("record-promotion", run, promotion_path).returncode == 0
    receipt = json.loads(promotion_path.read_text())
    Path(receipt["review"]["path"]).write_text("tampered\n")

    result = invoke("status", run)

    assert result.returncode == 2
    assert "recorded promotion review has SHA-256" in result.stderr
