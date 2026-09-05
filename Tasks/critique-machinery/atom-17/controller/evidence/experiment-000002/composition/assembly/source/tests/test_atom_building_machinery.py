import hashlib
import importlib.util
import json
import base64
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


def test_installed_controller_starts_without_repository_modules_at_import_time(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "schema.py"
    source.write_text("FIELD = 'count'\n")
    installed = tmp_path / "client" / "skills" / "atom-building-machinery" / "scripts"
    installed.mkdir(parents=True)
    controller = installed / "atom_controller.py"
    shutil.copy2(CONTROLLER, controller)
    request = tmp_path / "request.json"
    write_json(request, {
        "schema_version": 1,
        "atomic_step_id": "installed-runtime",
        "outcome": "installed controller starts",
        "practical_value": "both client projections can run",
        "stopping_condition": "start succeeds",
        "allowed_paths": ["schema.py"],
        "captured_cases": [{
            "case_id": "installed-start",
            "source_ref": "schema.py",
            "sha256": "fdd74b57182cfe530eb425366470d6a5ce5f0e69986757955fc9a90dc4cbd532",
            "kind": "success",
            "expected_outcome": "installed controller reaches the experiment stage",
        }, {
            "case_id": "installed-refusal",
            "source_ref": "schema.py",
            "sha256": "fdd74b57182cfe530eb425366470d6a5ce5f0e69986757955fc9a90dc4cbd532",
            "kind": "failure",
            "expected_outcome": "installed controller keeps its normal refusal gates",
        }],
        "contract_surface": {"kind": "render"},
    })
    completed = subprocess.run(
        [sys.executable, str(controller), "start", str(request), str(tmp_path / "run")],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["stage"] == "experiment"


@pytest.fixture
def controller_module() -> object:
    spec = importlib.util.spec_from_file_location("atom_controller_under_test", CONTROLLER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observed_operator() -> dict[str, object]:
    helper_sha256 = "1" * 64
    return {
        "login_user": "kamenkamenov",
        "uid": 501,
        "approval_ui": "native-macos-window",
        "authentication_policy": "device-owner-authentication",
        "client_projection": "codex",
        "helper_path": str(
            Path.home()
            / ".codex/skills/atom-building-machinery/scripts/prose_waiver_approval"
        ),
        "helper_sha256": helper_sha256,
        "parent_process_name": "Python",
        "parent_process_pid": 4321,
        "observed_at": "2026-09-05T12:00:00.000Z",
        "initiating_harness_markers": ["CODEX_SESSION_ID"],
    }


def native_authorization(context: dict[str, object], choice: str = "waive") -> dict[str, object]:
    choices = {
        "waive": (
            "I authorize this exact validation request to start as a recorded prose exception. "
            "This does not authorize promotion, operational use, another field, or another atom."
        ),
        "decline": (
            "I do not authorize this request to start while it reads prose. "
            "It must use a structured field before proceeding."
        ),
    }
    payload = {
        **context,
        "meanings": choices,
        "choice": choice,
        "adopted_statement": choices.get(choice, "invalid helper choice"),
        "date": "2026-09-05",
        "operator": observed_operator(),
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": 1,
        "status": "authorized",
        "helper_version": 1,
        "service": "memory-knowledge.atom-building.prose-waiver.native-v1",
        "signed_payload_base64": base64.b64encode(payload_bytes).decode(),
        "signed_payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "nonce": "2" * 64,
        "digest": "3" * 64,
    }


def test_native_authorization_context_and_payload_bind_atomic_step(
    tmp_path: Path,
    controller_module: object,
) -> None:
    context = controller_module._authorization_context(
        "atom-visible-to-operator",
        "a" * 64,
        tmp_path,
        ["proof_building_order"],
    )
    assert context == {
        "schema_version": 1,
        "atomic_step_id": "atom-visible-to-operator",
        "request_sha256": "a" * 64,
        "repository_root": str(tmp_path),
        "fields": ["proof_building_order"],
    }
    authorization = native_authorization(context)
    proof = controller_module._validated_presence(
        {
            "scheme": "native-macos-device-owner-hmac-v1",
            "service": authorization["service"],
            "helper_version": authorization["helper_version"],
            "helper_sha256": observed_operator()["helper_sha256"],
            "signed_payload_base64": authorization["signed_payload_base64"],
            "signed_payload_sha256": authorization["signed_payload_sha256"],
            "nonce": authorization["nonce"],
            "digest": authorization["digest"],
        },
        "test",
    )
    with pytest.raises(Exception, match="atomic_step_id differs from the bound request"):
        controller_module._validated_signed_authorization(
            proof,
            {**context, "atomic_step_id": "another-atom"},
            "test",
        )


def test_existing_atom_14_native_receipt_remains_valid_for_its_exact_request(
    controller_module: object,
) -> None:
    receipt = json.loads((
        ROOT
        / "Tasks/critique-machinery/atom-14/operator-validation/native-interview/prose-waiver-receipt.json"
    ).read_text())
    proof = controller_module._validated_presence(receipt["presence_proof"], "test")
    signed = controller_module._validated_signed_authorization(
        proof,
        {
            "schema_version": 1,
            "atomic_step_id": "prose-waiver-proves-operator-presence",
            "request_sha256": receipt["request_sha256"],
            "repository_root": receipt["repository_root"],
            "fields": receipt["fields"],
        },
        "test",
    )
    assert signed["choice"] == "waive"


def test_native_helper_source_displays_and_signs_exact_atom_identity() -> None:
    source = (ROOT / "skills/atom-building-machinery/scripts/prose_waiver_approval.swift").read_text()
    assert '"atomic_step_id"' in source
    assert 'Atom: \\(atomicStep)' in source
    assert 'Request SHA-256: \\(requestSHA)' in source
    assert 'for atom \\(atomicStep), request \\(requestSHA)' in source
    assert '"atomic_step_id": atomicStep' in source
    assert '?? "unavailable"' in source


def test_installed_controller_resolves_only_hash_bound_managed_support(
    tmp_path: Path,
) -> None:
    installed = tmp_path / "client/skills/atom-building-machinery/scripts"
    installed.mkdir(parents=True)
    copied = installed / "atom_controller.py"
    shutil.copy2(CONTROLLER, copied)
    support = tmp_path / "source-repository"
    (support / "scripts").mkdir(parents=True)
    files = {}
    for name, content in (
        ("scripts/blocker_catalog.py", "BLOCKER = 1\n"),
        ("scripts/work_memory.py", "MEMORY = 1\n"),
    ):
        path = support / name
        path.write_text(content)
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(tmp_path / "client/.managed-skills-source.json", {
        "schema_version": 1,
        "source_repository_root": str(support),
        "support_files": files,
    })
    installed_module = load_module = importlib.util.spec_from_file_location(
        "installed_atom_controller_under_test", copied
    )
    assert load_module is not None and load_module.loader is not None
    module = importlib.util.module_from_spec(load_module)
    load_module.loader.exec_module(module)
    assert module._blocker_support_root("test") == support
    (support / "scripts/work_memory.py").write_text("TAMPERED = 1\n")
    with pytest.raises(Exception, match="managed blocker support hash differs"):
        module._blocker_support_root("test")


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


def test_prose_target_requires_native_authenticated_presence_round_trip(
    tmp_path: Path,
    assembly_fixture: tuple[Path, dict[str, object], str],
    controller_module: object,
    monkeypatch: pytest.MonkeyPatch,
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

    monkeypatch.chdir(tmp_path)
    verified: list[dict[str, object]] = []
    monkeypatch.setattr(controller_module, "_native_verify", lambda proof: verified.append(proof))
    interview = tmp_path / "waiver-interview"
    authorized = controller_module.prose_waiver_interview(
        request_path,
        interview,
        approval_fn=lambda context: native_authorization(context),
    )
    assert authorized["status"] == "completed"
    started = controller_module.start(request_path, tmp_path / "waived", None, interview)
    waiver = started["prose_waiver"]
    assert waiver["operator"] == observed_operator()
    assert waiver["words"] == (
        "I authorize this exact validation request to start as a recorded prose exception. "
        "This does not authorize promotion, operational use, another field, or another atom."
    )
    assert waiver["date"] == "2026-09-05"
    receipt = json.loads((interview / "prose-waiver-receipt.json").read_text())
    assert receipt["operator_choice"] == "waive"
    assert receipt["words"] == waiver["words"]
    assert receipt["presence_proof"]["scheme"] == "native-macos-device-owner-hmac-v1"
    assert receipt["presence_proof"]["helper_sha256"] == "1" * 64
    assert len(verified) == 1
    assert verified[0] == receipt["presence_proof"]
    assert "secret" not in json.dumps(receipt).lower()


def test_declined_prose_choice_keeps_the_request_blocked(
    tmp_path: Path,
    assembly_fixture: tuple[Path, dict[str, object], str],
    controller_module: object,
    monkeypatch: pytest.MonkeyPatch,
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

    monkeypatch.chdir(tmp_path)
    declined = controller_module.prose_waiver_interview(
        request_path,
        interview,
        approval_fn=lambda context: native_authorization(context, "decline"),
    )
    assert declined["status"] == "declined"
    assert not (interview / "prose-waiver-receipt.json").exists()
    with pytest.raises(Exception, match="operator 'kamenkamenov' chose 'decline'.*remains blocked"):
        controller_module.start(request_path, tmp_path / "blocked", None, interview)
    assert not (tmp_path / "blocked").exists()


def test_prose_waiver_interview_refuses_invalid_helper_choice_or_changed_request(
    tmp_path: Path,
    assembly_fixture: tuple[Path, dict[str, object], str],
    controller_module: object,
    monkeypatch: pytest.MonkeyPatch,
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

    monkeypatch.chdir(tmp_path)
    with pytest.raises(Exception, match="choice must be exactly 'waive' or 'decline'"):
        controller_module.prose_waiver_interview(
            request_path,
            interview,
            approval_fn=lambda context: native_authorization(context, "yes"),
        )
    assert len((interview / "ledger.jsonl").read_text().splitlines()) == 1
    value["outcome"] = "changed after the owner question"
    write_json(request_path, value)
    with pytest.raises(Exception, match="differs from the question presented"):
        controller_module.prose_waiver_interview(
            request_path,
            interview,
            approval_fn=lambda context: native_authorization(context),
        )
    assert len((interview / "ledger.jsonl").read_text().splitlines()) == 1


def test_start_rejects_presence_proof_that_native_helper_cannot_verify(
    tmp_path: Path,
    assembly_fixture: tuple[Path, dict[str, object], str],
    controller_module: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_tactical_schema(tmp_path)
    value = request(assembly_fixture[1])
    value["contract_surface"] = validation_surface(
        ("proof_building_order", "prose", "src/up_harness/tactical_roadmap.py::SECTION_KEYS"),
    )
    request_path = tmp_path / "request.json"
    write_json(request_path, value)
    monkeypatch.chdir(tmp_path)
    interview = tmp_path / "waiver-interview"
    controller_module.prose_waiver_interview(
        request_path,
        interview,
        approval_fn=lambda context: native_authorization(context),
    )
    def reject(_: dict[str, object]) -> None:
        raise controller_module.AtomError("start", "receipt proof does not match the protected approval key")

    monkeypatch.setattr(controller_module, "_native_verify", reject)
    with pytest.raises(Exception, match="receipt proof does not match the protected approval key"):
        controller_module.start(request_path, tmp_path / "forged", None, interview)
    assert not (tmp_path / "forged").exists()


def test_prose_waiver_receipt_cannot_cross_to_changed_request(
    tmp_path: Path,
    assembly_fixture: tuple[Path, dict[str, object], str],
    controller_module: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_tactical_schema(tmp_path)
    first = request(assembly_fixture[1])
    first["contract_surface"] = validation_surface(
        ("proof_building_order", "prose", "src/up_harness/tactical_roadmap.py::SECTION_KEYS"),
    )
    first_path = tmp_path / "first.json"
    write_json(first_path, first)
    monkeypatch.chdir(tmp_path)
    interview = tmp_path / "waiver-interview"
    controller_module.prose_waiver_interview(
        first_path,
        interview,
        approval_fn=lambda context: native_authorization(context),
    )
    second = dict(first)
    second["outcome"] = "a genuinely different request"
    second_path = tmp_path / "second.json"
    write_json(second_path, second)
    with pytest.raises(Exception, match="bound to a different request"):
        controller_module.start(second_path, tmp_path / "crossed", None, interview)
    assert not (tmp_path / "crossed").exists()


def test_native_helper_refuses_model_supplied_choice_without_opening_ui() -> None:
    helper = ROOT / "skills/atom-building-machinery/scripts/prose_waiver_approval"
    result = subprocess.run(
        [str(helper), "authorize", "waive"],
        input=b"{}",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert b"decision cannot be supplied by arguments" in result.stderr


def test_introduced_field_starts_and_must_resolve_before_promotion(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str], controller_module: object
) -> None:
    """Atom 16 (2026-09-05): round 5 of the S12 roadmap adds fields (a card's approver, a stage
    list, a widening month). The real request s12-approver-named was refused at start because
    the field did not exist yet; adding it first would hide the atom's change from its record."""
    write_tactical_schema(tmp_path)
    value = request(assembly_fixture[1])
    value["contract_surface"] = validation_surface(
        ("ownership[].approver", "pinned-string", "src/up_harness/tactical_roadmap.py::DOOR_FORM"),
    )
    value["contract_surface"]["fields"][0]["introduced"] = True
    request_path = tmp_path / "request.json"
    write_json(request_path, value)

    result = invoke("start", request_path, tmp_path / "run", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["contract_surface"]["fields"][0]["introduced"] is True
    assert read_state(tmp_path / "run")["contract_surface"]["fields"][0]["field"] == "ownership[].approver"

    # the leaf is not in the schema yet: promotion-time resolution refuses, naming the field
    with pytest.raises(controller_module.AtomError) as refused:
        controller_module._validate_request(
            value, repository_root=tmp_path, stage="record-promotion", require_introduced_resolved=True
        )
    assert "introduced field 'ownership[].approver' still does not resolve" in str(refused.value)
    assert "canonical module must carry it" in str(refused.value)

    # once the canonical module carries the leaf, the same request resolves at promotion
    schema = tmp_path / "src" / "up_harness" / "tactical_roadmap.py"
    schema.write_text(schema.read_text().replace(
        "OWNERSHIP_FIELDS = ('element', 'owner')", "OWNERSHIP_FIELDS = ('element', 'owner', 'approver')"
    ))
    resolved = controller_module._validate_request(
        value, repository_root=tmp_path, stage="record-promotion", require_introduced_resolved=True
    )
    assert resolved["contract_surface"]["fields"][0]["introduced"] is True


def test_a_run_with_an_introduced_field_loads_once_the_module_carries_it(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    """Atom 17 (2026-09-05, CM-B13): round-5 atom D started with its approver field introduced; when the
    canonical module gained the field, status and change-surface refused the run as 'already resolves;
    declare it without introduced'. A started run keeps loading; only a new start is refused."""
    write_tactical_schema(tmp_path)
    value = request(assembly_fixture[1])
    value["contract_surface"] = validation_surface(
        ("ownership[].approver", "pinned-string", "src/up_harness/tactical_roadmap.py::DOOR_FORM"),
    )
    value["contract_surface"]["fields"][0]["introduced"] = True
    request_path = tmp_path / "request.json"
    write_json(request_path, value)
    assert invoke("start", request_path, tmp_path / "run", cwd=tmp_path).returncode == 0

    schema = tmp_path / "src" / "up_harness" / "tactical_roadmap.py"
    schema.write_text(schema.read_text().replace(
        "OWNERSHIP_FIELDS = ('element', 'owner')", "OWNERSHIP_FIELDS = ('element', 'owner', 'approver')"
    ))
    loaded = invoke("status", tmp_path / "run", cwd=tmp_path)
    assert loaded.returncode == 0, loaded.stderr
    assert json.loads(loaded.stdout)["contract_surface"]["fields"][0]["introduced"] is True
    surface = invoke("change-surface", tmp_path / "run", tmp_path / "surface.json", cwd=tmp_path)
    assert surface.returncode == 0, surface.stderr

    # a NEW start declaring the now-existing field as introduced is still refused
    again = invoke("start", request_path, tmp_path / "again", cwd=tmp_path)
    assert again.returncode == 2
    assert "already resolves at 'approver'" in again.stderr


def test_introduced_field_that_already_exists_or_is_misspelled_is_refused(
    tmp_path: Path, assembly_fixture: tuple[Path, dict[str, object], str]
) -> None:
    write_tactical_schema(tmp_path)
    value = request(assembly_fixture[1])
    value["contract_surface"] = validation_surface(
        ("ownership[].owner", "pinned-string", "src/up_harness/tactical_roadmap.py::DOOR_FORM"),
    )
    value["contract_surface"]["fields"][0]["introduced"] = True
    request_path = tmp_path / "request.json"
    write_json(request_path, value)
    existing = invoke("start", request_path, tmp_path / "existing", cwd=tmp_path)
    assert existing.returncode == 2
    assert "already resolves at 'owner'" in existing.stderr
    assert "declare it without 'introduced'" in existing.stderr

    value["contract_surface"]["fields"][0]["introduced"] = "yes"
    write_json(request_path, value)
    wrong = invoke("start", request_path, tmp_path / "wrong", cwd=tmp_path)
    assert wrong.returncode == 2
    assert "write true for a field this atom introduces" in wrong.stderr

    # a misspelling without the flag is refused exactly as before
    value["contract_surface"] = validation_surface(
        ("ownership[].owenr", "pinned-string", "src/up_harness/tactical_roadmap.py::DOOR_FORM"),
    )
    write_json(request_path, value)
    misspelled = invoke("start", request_path, tmp_path / "misspelled", cwd=tmp_path)
    assert misspelled.returncode == 2
    assert "available keys are ['element', 'owner']" in misspelled.stderr


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
