import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date as calendar_date
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


def invoke(
    *args: object,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CONTROLLER), *(str(arg) for arg in args)],
        cwd=cwd,
        text=True,
        input=input_text,
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
        "contract_surface": {"kind": "render"},
        "allowed_paths": ["src/records", "tests/records"],
        "captured_cases": [
            {
                "case_id": case["id"],
                "source_ref": case["source_ref"],
                "sha256": case["sha256"],
                "kind": case["kind"],
                "expected_outcome": case["expected_outcome"],
            }
            for case in manifest["captured_cases"]
        ],
    }


def write_tactical_schema(root: Path) -> None:
    path = root / "src" / "up_harness" / "tactical_roadmap.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "import re\n"
        "ROADMAP_PHASES = ('Pre-Seed', 'Launch', 'Sustain', 'Amplify')\n"
        "ACTIVATION_CARD_FIELDS = ('kpi', 'phase', 'month')\n"
        "CALENDAR_FIELDS = ('month', 'phase')\n"
        "OWNERSHIP_FIELDS = ('element', 'owner')\n"
        "SECTION_KEYS = ('activation_cards', 'calendar', 'proof_building_order', 'ownership')\n"
        "DOOR_FORM = re.compile(r'^unassigned — .+ by .+$')\n"
    )


def validation_surface(*fields: tuple[str, str, str]) -> dict[str, object]:
    return {
        "kind": "validation",
        "deliverable": "tactical_roadmap",
        "fields": [
            {"field": field, "shape": shape, "shape_source": source}
            for field, shape, source in fields
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
            "contract_surface": read_state(run)["contract_surface"],
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


def test_start_refuses_run_below_allowed_product_path(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    _, manifest, _ = assembly_fixture
    repository = tmp_path / "repository"
    repository.mkdir()
    request_path = repository / "request.json"
    write_json(request_path, request(manifest))
    run = repository / "src" / "records" / "atom-run"

    result = invoke("start", request_path, run, cwd=repository)

    assert result.returncode == 2
    assert "overlaps allowed_paths" in result.stderr
    assert not run.exists()


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


def test_validation_snapshots_survive_caller_evidence_change_and_refuse_snapshot_tamper(
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
    Path(receipt["cases"][0]["evidence"][0]["path"]).write_text("changed caller evidence\n")
    assert invoke("authorize-next", run).returncode == 0

    recorded = json.loads((run / "ledger.jsonl").read_text().splitlines()[-1])["payload"]
    snapshot = Path(recorded["case_evidence"][0]["evidence"][0]["path"])
    assert snapshot.is_relative_to(run / "evidence")
    snapshot.write_text("tampered snapshot\n")
    result = invoke("authorize-next", run)
    assert result.returncode == 2
    assert "recorded validation evidence" in result.stderr
    assert "has SHA-256" in result.stderr


def test_promotion_evidence_snapshot_survives_caller_change_and_refuses_tamper(
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
    assert read_state(run)["stage"] == "validation"

    payload = json.loads((run / "ledger.jsonl").read_text().splitlines()[-1])["payload"]
    Path(payload["evidence"][0]["path"]).write_text("tampered snapshot\n")
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


def test_superseded_legacy_failed_evidence_drift_is_reported_and_recoverable(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    first_experiment = tmp_path / "first-experiment"
    experiment(first_experiment, assembly_fixture)
    state = json.loads(invoke("record-experiment", run, first_experiment).stdout)
    promotion_path = tmp_path / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    state = json.loads(invoke("record-promotion", run, promotion_path).stdout)
    validation_path = tmp_path / "failed-validation.json"
    validation_receipt(validation_path, state, "not-satisfied")
    assert invoke("record-validation", run, validation_path).returncode == 0

    recorded = json.loads((run / "ledger.jsonl").read_text().splitlines()[-1])["payload"]
    legacy_evidence = recorded["case_evidence"][0]["evidence"][0]
    original_snapshot = Path(legacy_evidence["path"])
    external_path = tmp_path / "legacy-external-evidence.json"
    shutil.copyfile(original_snapshot, external_path)
    legacy_evidence["path"] = str(external_path)
    records = [json.loads(line) for line in (run / "ledger.jsonl").read_text().splitlines()]
    records[-1]["payload"]["case_evidence"][0]["evidence"][0] = legacy_evidence
    previous = None
    lines = []
    for index, record in enumerate(records, start=1):
        record["sequence"] = index
        record["previous_event_sha256"] = previous
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        lines.append(line)
        previous = hashlib.sha256(line.encode()).hexdigest()
    (run / "ledger.jsonl").write_text("".join(lines))

    second_experiment = tmp_path / "second-experiment"
    experiment(second_experiment, assembly_fixture)
    assert invoke("record-experiment", run, second_experiment).returncode == 0
    external_path.write_text("changed superseded evidence\n")

    result = invoke("status", run)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["stage"] == "promotion"
    assert len(state["legacy_validation_evidence_drift"]) == 1
    assert state["legacy_validation_evidence_drift"][0]["status"] == "superseded-external-evidence-drift"


def test_current_legacy_failed_evidence_drift_remains_strict(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    state = json.loads(invoke("record-experiment", run, experiment_path).stdout)
    promotion_path = tmp_path / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    state = json.loads(invoke("record-promotion", run, promotion_path).stdout)
    validation_path = tmp_path / "failed-validation.json"
    validation_receipt(validation_path, state, "not-satisfied")
    assert invoke("record-validation", run, validation_path).returncode == 0

    recorded = json.loads((run / "ledger.jsonl").read_text().splitlines()[-1])["payload"]
    Path(recorded["case_evidence"][0]["evidence"][0]["path"]).write_text("changed\n")
    result = invoke("status", run)
    assert result.returncode == 2
    assert "recorded validation evidence" in result.stderr


def test_tampered_ledger_is_refused(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    ledger = run / "ledger.jsonl"
    ledger.write_text(ledger.read_text().replace(f'"{ATOM_ID}"', '"atom-X"'))
    result = invoke("status", run)
    assert result.returncode == 2
    assert f"require preserved request identity '{ATOM_ID}'" in result.stderr


def test_validation_receipt_snapshot_survives_caller_change_and_remains_strict(
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
    assert invoke("authorize-next", run).returncode == 0

    recorded = json.loads((run / "ledger.jsonl").read_text().splitlines()[-1])["payload"]
    Path(recorded["receipt_path"]).write_text("{}\n")
    result = invoke("authorize-next", run)
    assert result.returncode == 2
    assert "recorded validation receipt has SHA-256" in result.stderr


def test_experiment_snapshot_survives_caller_assembly_removal(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    assert invoke("record-experiment", run, experiment_path).returncode == 0
    (experiment_path / "composition" / "assembly").rename(
        experiment_path / "composition" / "removed-assembly"
    )

    assert read_state(run)["stage"] == "promotion"


def test_experiment_snapshot_survives_source_removal_and_refuses_tamper(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    write_json(experiment_path / "unrelated.json", {"not": "admitted"})
    assert invoke("record-experiment", run, experiment_path).returncode == 0
    payload = json.loads((run / "ledger.jsonl").read_text().splitlines()[-1])["payload"]
    snapshot = Path(payload["experiment_path"])
    assert snapshot.is_relative_to(run / "evidence")
    assert not (snapshot / "unrelated.json").exists()

    experiment_path.rename(tmp_path / "removed-experiment")
    assert read_state(run)["stage"] == "promotion"
    (snapshot / "development-probe-summary.json").write_text("tampered\n")
    assert invoke("status", run).returncode == 2


def test_promotion_snapshot_survives_source_removal_and_refuses_tamper(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)
    state = json.loads(invoke("record-experiment", run, experiment_path).stdout)
    source = tmp_path / "promotion-source"
    promotion_path = source / "promotion.json"
    promotion_receipt(promotion_path, run, state)
    write_json(source / "unrelated.json", {"not": "admitted"})
    assert invoke("record-promotion", run, promotion_path).returncode == 0
    payload = json.loads((run / "ledger.jsonl").read_text().splitlines()[-1])["payload"]
    paths = [payload["receipt_path"], payload["change_surface"]["path"], payload["review"]["path"]]
    paths.extend(item["path"] for item in payload["evidence"])
    assert all(Path(path).is_relative_to(run / "evidence") for path in paths)
    assert not any(path.name == "unrelated.json" for path in (run / "evidence").rglob("*"))

    shutil.rmtree(source)
    assert read_state(run)["stage"] == "validation"
    Path(payload["evidence"][0]["path"]).write_text("tampered\n")
    assert invoke("status", run).returncode == 2


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


def test_promotion_review_snapshot_survives_caller_change_and_refuses_tamper(
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
    assert read_state(run)["stage"] == "validation"

    payload = json.loads((run / "ledger.jsonl").read_text().splitlines()[-1])["payload"]
    Path(payload["review"]["path"]).write_text("tampered snapshot\n")
    result = invoke("status", run)

    assert result.returncode == 2
    assert "recorded promotion review has SHA-256" in result.stderr


def test_current_experiment_stage_receipts_advance(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    run = start(tmp_path, assembly_fixture)
    experiment_path = tmp_path / "current-experiment"
    experiment(experiment_path, assembly_fixture)
    summary_path = experiment_path / "development-probe-summary.json"
    summary = json.loads(summary_path.read_text())
    for receipt in summary["stages"]:
        receipt.update({
            "duration_ms": 1,
            "timeout_ms": 2700000,
            "timed_out": False,
            "stdout_sha256": "2" * 64,
            "stderr_sha256": "3" * 64,
            "timeout": None,
            "timeout_sha256": None,
        })
    write_json(summary_path, summary)

    result = invoke("record-experiment", run, experiment_path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["stage"] == "promotion"


def test_superseded_run_carries_earliest_baseline_and_names_chain(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    first = start(tmp_path, assembly_fixture)
    original_baseline = (first / "inputs" / "change-baseline.json").read_bytes()
    write_json(tmp_path / "src" / "records" / "save.py", {"version": "promoted-before-rebuild"})
    second = tmp_path / "run-2"

    result = invoke(
        "start", tmp_path / "request.json", second, "--supersedes", first, cwd=tmp_path
    )

    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["supersession_chain"] == [str(first), str(second)]
    assert state["supersession_chain_closed"] is False
    assert (second / "inputs" / "change-baseline.json").read_bytes() == original_baseline
    surface = tmp_path / "superseded-surface.json"
    assert invoke("change-surface", second, surface).returncode == 0
    assert [item["path"] for item in json.loads(surface.read_text())["changes"]] == [
        "src/records/save.py"
    ]


def test_supersession_refuses_different_atom_complete_run_and_damaged_chain(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    first = start(tmp_path, assembly_fixture)
    mismatched_request = request(assembly_fixture[1])
    mismatched_request["atomic_step_id"] = "different-atom"
    write_json(tmp_path / "different-request.json", mismatched_request)
    mismatch = invoke(
        "start", tmp_path / "different-request.json", tmp_path / "mismatch-run",
        "--supersedes", first, cwd=tmp_path,
    )
    assert mismatch.returncode == 2
    assert "previous run atomic_step_id" in mismatch.stderr

    second = tmp_path / "run-2"
    assert invoke(
        "start", tmp_path / "request.json", second, "--supersedes", first, cwd=tmp_path
    ).returncode == 0
    baseline = first / "inputs" / "change-baseline.json"
    baseline.write_bytes(baseline.read_bytes() + b" ")
    damaged = invoke(
        "start", tmp_path / "request.json", tmp_path / "run-3",
        "--supersedes", second, cwd=tmp_path,
    )
    assert damaged.returncode == 2
    assert "Atom Building Machinery refused at start" in damaged.stderr
    assert "superseded change baseline has SHA-256" in damaged.stderr

    complete_root = tmp_path / "complete"
    complete_root.mkdir()
    complete_run = start(complete_root, assembly_fixture)
    experiment_path = complete_root / "experiment"
    experiment(experiment_path, assembly_fixture)
    state = json.loads(invoke("record-experiment", complete_run, experiment_path).stdout)
    promotion_path = complete_root / "promotion.json"
    promotion_receipt(promotion_path, complete_run, state)
    state = json.loads(invoke("record-promotion", complete_run, promotion_path).stdout)
    validation_path = complete_root / "validation.json"
    validation_receipt(validation_path, state)
    assert invoke("record-validation", complete_run, validation_path).returncode == 0
    completed = invoke(
        "start", complete_root / "request.json", complete_root / "successor",
        "--supersedes", complete_run, cwd=complete_root,
    )
    assert completed.returncode == 2
    assert "is complete and cannot be superseded" in completed.stderr


def test_authorize_next_closes_supersession_chain_once(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    first = start(tmp_path, assembly_fixture)
    second = tmp_path / "run-2"
    assert invoke(
        "start", tmp_path / "request.json", second, "--supersedes", first, cwd=tmp_path
    ).returncode == 0
    experiment_path = tmp_path / "experiment-2"
    experiment(experiment_path, assembly_fixture)
    state = json.loads(invoke("record-experiment", second, experiment_path).stdout)
    promotion_path = tmp_path / "promotion-2.json"
    promotion_receipt(promotion_path, second, state)
    state = json.loads(invoke("record-promotion", second, promotion_path).stdout)
    validation_path = tmp_path / "validation-2.json"
    validation_receipt(validation_path, state)
    assert invoke("record-validation", second, validation_path).returncode == 0

    result = invoke("authorize-next", second)

    assert result.returncode == 0, result.stderr
    authorized = json.loads(result.stdout)
    assert authorized["supersession_chain"] == [str(first), str(second)]
    assert authorized["supersession_chain_closed"] is True
    lines_after_first = (second / "ledger.jsonl").read_text().splitlines()
    assert json.loads(lines_after_first[-1])["event"] == "supersession-chain-closed"
    assert invoke("authorize-next", second).returncode == 0
    assert (second / "ledger.jsonl").read_text().splitlines() == lines_after_first


def test_new_start_requires_contract_surface(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    value = request(assembly_fixture[1])
    del value["contract_surface"]
    request_path = tmp_path / "request.json"
    write_json(request_path, value)

    result = invoke("start", request_path, tmp_path / "run", cwd=tmp_path)

    assert result.returncode == 2
    assert "has no contract_surface" in result.stderr
    assert not (tmp_path / "run").exists()


def test_validation_surface_resolves_real_shapes_and_status_round_trips_it(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    write_tactical_schema(tmp_path)
    value = request(assembly_fixture[1])
    value["contract_surface"] = validation_surface(
        (
            "ownership[].owner",
            "pinned-string",
            "src/up_harness/tactical_roadmap.py::DOOR_FORM",
        ),
        (
            "activation_cards[].month",
            "integer",
            "src/up_harness/tactical_roadmap.py::ACTIVATION_CARD_FIELDS",
        ),
        (
            "activation_cards[].phase",
            "enum",
            "src/up_harness/tactical_roadmap.py::ROADMAP_PHASES",
        ),
    )
    request_path = tmp_path / "request.json"
    write_json(request_path, value)

    result = invoke("start", request_path, tmp_path / "run", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["contract_surface"] == value["contract_surface"]
    assert state["prose_waiver"] is None


def test_validation_atom_can_declare_the_controllers_own_contract_surface(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    schema = tmp_path / "skills" / "atom-building-machinery" / "scripts" / "atom_controller.py"
    schema.parent.mkdir(parents=True)
    shutil.copy2(CONTROLLER, schema)
    value = request(assembly_fixture[1])
    value["contract_surface"] = {
        "kind": "validation",
        "deliverable": "atom_controller",
        "fields": [
            {
                "field": "contract_surface",
                "shape": "object",
                "shape_source": "skills/atom-building-machinery/scripts/atom_controller.py::REQUEST_FIELDS",
            }
        ],
    }
    request_path = tmp_path / "request.json"
    write_json(request_path, value)

    result = invoke("start", request_path, tmp_path / "run", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["contract_surface"] == value["contract_surface"]


def test_prose_target_requires_code_interview_and_owner_choice_round_trip(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    write_tactical_schema(tmp_path)
    value = request(assembly_fixture[1])
    value["contract_surface"] = validation_surface(
        (
            "proof_building_order",
            "prose",
            "src/up_harness/tactical_roadmap.py::SECTION_KEYS",
        ),
    )
    request_path = tmp_path / "request.json"
    write_json(request_path, value)

    refused = invoke("start", request_path, tmp_path / "refused", cwd=tmp_path)

    assert refused.returncode == 2
    assert "proof_building_order" in refused.stderr
    assert "misread three real runs" in refused.stderr
    assert "structured field" in refused.stderr
    assert "prose-waiver-interview" in refused.stderr
    value["prose_waiver"] = {
        "by": "Kamen Kamenov",
        "words": "a model must not be able to write these words itself",
        "date": "2026-09-04",
    }
    write_json(request_path, value)
    direct = invoke("start", request_path, tmp_path / "direct-waiver", cwd=tmp_path)
    assert direct.returncode == 2
    assert "hand-written prose_waiver" in direct.stderr
    del value["prose_waiver"]
    write_json(request_path, value)

    interview = tmp_path / "waiver-interview"
    authorized = invoke(
        "prose-waiver-interview",
        request_path,
        interview,
        cwd=tmp_path,
        input_text="waive\n",
    )
    assert authorized.returncode == 0, authorized.stderr
    assert json.loads(authorized.stdout.splitlines()[-1])["status"] == "completed"
    started = invoke(
        "start",
        request_path,
        tmp_path / "waived",
        "--prose-waiver-interview",
        interview,
        cwd=tmp_path,
    )
    assert started.returncode == 0, started.stderr
    waiver = json.loads(started.stdout)["prose_waiver"]
    assert waiver["by"] == "Kamen Kamenov"
    assert waiver["words"] == (
        "I authorize this exact validation request to start as a recorded prose exception. "
        "This does not authorize promotion, operational use, another field, or another atom."
    )
    assert waiver["date"] == calendar_date.today().isoformat()
    receipt = json.loads((interview / "prose-waiver-receipt.json").read_text())
    assert receipt["operator_choice"] == "waive"
    assert receipt["words"] == waiver["words"]


def test_declined_prose_choice_keeps_the_request_blocked(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    write_tactical_schema(tmp_path)
    value = request(assembly_fixture[1])
    value["contract_surface"] = validation_surface(
        (
            "proof_building_order",
            "prose",
            "src/up_harness/tactical_roadmap.py::SECTION_KEYS",
        ),
    )
    request_path = tmp_path / "request.json"
    write_json(request_path, value)
    interview = tmp_path / "waiver-interview"

    declined = invoke(
        "prose-waiver-interview",
        request_path,
        interview,
        cwd=tmp_path,
        input_text="decline\n",
    )
    assert declined.returncode == 0, declined.stderr
    assert json.loads(declined.stdout.splitlines()[-1])["status"] == "declined"
    assert not (interview / "prose-waiver-receipt.json").exists()
    refused = invoke(
        "start",
        request_path,
        tmp_path / "blocked",
        "--prose-waiver-interview",
        interview,
        cwd=tmp_path,
    )
    assert refused.returncode == 2
    assert "Kamen Kamenov chose 'decline'" in refused.stderr
    assert "remains blocked until it uses a structured field" in refused.stderr
    assert not (tmp_path / "blocked").exists()


def test_prose_waiver_interview_refuses_invalid_or_changed_operator_boundary(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    write_tactical_schema(tmp_path)
    value = request(assembly_fixture[1])
    value["contract_surface"] = validation_surface(
        (
            "proof_building_order",
            "prose",
            "src/up_harness/tactical_roadmap.py::SECTION_KEYS",
        ),
    )
    request_path = tmp_path / "request.json"
    write_json(request_path, value)
    interview = tmp_path / "waiver-interview"

    invalid = invoke(
        "prose-waiver-interview",
        request_path,
        interview,
        cwd=tmp_path,
        input_text="yes\n",
    )
    assert invalid.returncode == 2
    assert "choose one word: 'waive' or 'decline'" in invalid.stderr
    assert len((interview / "ledger.jsonl").read_text().splitlines()) == 1
    value["outcome"] = "changed after the owner question"
    write_json(request_path, value)
    changed = invoke(
        "prose-waiver-interview",
        request_path,
        interview,
        cwd=tmp_path,
        input_text="waive\n",
    )
    assert changed.returncode == 2
    assert "differs from the question presented" in changed.stderr
    assert len((interview / "ledger.jsonl").read_text().splitlines()) == 1


def test_validation_surface_misspelling_names_available_keys(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    write_tactical_schema(tmp_path)
    value = request(assembly_fixture[1])
    value["contract_surface"] = validation_surface(
        (
            "ownership[].owenr",
            "pinned-string",
            "src/up_harness/tactical_roadmap.py::DOOR_FORM",
        ),
    )
    request_path = tmp_path / "request.json"
    write_json(request_path, value)

    result = invoke("start", request_path, tmp_path / "run", cwd=tmp_path)

    assert result.returncode == 2
    assert "ownership[].owenr" in result.stderr
    assert "available keys are ['element', 'owner']" in result.stderr


def test_record_experiment_reports_observed_keys_and_refuses_missing_declared_target(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    schema = tmp_path / "src" / "records" / "save.py"
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text("SECTION_KEYS = ('declared_target_xyz',)\n")
    write_json(tmp_path / "tests" / "records" / "test_save.py", {"version": "baseline"})
    value = request(assembly_fixture[1])
    value["contract_surface"] = {
        "kind": "validation",
        "deliverable": "save",
        "fields": [{
            "field": "declared_target_xyz",
            "shape": "object",
            "shape_source": "src/records/save.py::SECTION_KEYS",
        }],
    }
    request_path = tmp_path / "request.json"
    write_json(request_path, value)
    run = tmp_path / "run"
    assert invoke("start", request_path, run, cwd=tmp_path).returncode == 0
    experiment_path = tmp_path / "experiment"
    experiment(experiment_path, assembly_fixture)

    result = invoke("record-experiment", run, experiment_path)

    assert result.returncode == 2
    assert "declared_target_xyz" in result.stderr
    assert "observed payload keys were" in result.stderr
    assert read_state(run)["stage"] == "experiment"
