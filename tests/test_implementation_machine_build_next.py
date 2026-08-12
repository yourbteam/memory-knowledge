"""Focused contracts for Implementation Machinery acceleration paths."""
from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "implementation-machine"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SKILL))

spec = importlib.util.spec_from_file_location(
    "implementation_machine_build_next", SKILL / "build_next.py"
)
machine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(machine)


@pytest.fixture(autouse=True)
def _isolated_controller_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "IMPLEMENTATION_MACHINE_CONTROL_ROOT", str(tmp_path / "controller-state")
    )


def test_cli_never_writes_bytecode_into_its_managed_skill_tree(tmp_path: Path):
    source = (SKILL / "build_next.py").read_text()
    assert source.index("sys.dont_write_bytecode = True") < source.index(
        "from client_model_policy import validate_reader_command"
    )
    staged = tmp_path / "implementation-machine"
    shutil.copytree(SKILL, staged, ignore=shutil.ignore_patterns("__pycache__"))
    environment = os.environ.copy()
    environment.pop("PYTHONDONTWRITEBYTECODE", None)

    script = staged / "build_next.py"
    probe = (
        "import runpy,sys; "
        "sys.dont_write_bytecode=False; "
        f"sys.path.insert(0, {str(staged)!r}); "
        f"sys.argv=[{str(script)!r}, '--help']; "
        f"runpy.run_path({str(script)!r}, run_name='__main__')"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert not (staged / "__pycache__").exists()


def _order(path: Path, requirement: str = "Restricted material must never escape.") -> dict:
    return {
        "work": [
            {
                "round": 1,
                "requirement_id": "r1",
                "requirement": requirement,
                "parts": [
                    {
                        "part_id": "r1.p1",
                        "part": requirement,
                        "seen_at": f'{path}:2 — "needle",',
                    }
                ],
                "part_count": 1,
            }
        ]
    }


def _record(part_id: str = "r1.p1", answer: str = "yes") -> dict:
    return {
        "part_id": part_id,
        "answer": answer,
        "citations": [
            {"where": "target.py", "line": 2, "text": "    return 'needle'"}
        ],
        "looked_at": "target.py and its callers",
    }


def _seed_change(work: Path, built: Path) -> Path:
    out = work / "build-r1"
    out.mkdir(parents=True)
    (out / "tests-before.json").write_text(
        json.dumps({"command": "tests", "exit_code": 0, "failed": [], "names": []})
    )
    (out / "change.json").write_text(
        json.dumps(
            {
                "files": ["target.py"],
                "what_changed": "PRIVATE BUILDER CONCLUSION",
                "tests_changed": [],
                "left_alone": "nothing",
            }
        )
    )
    return out


def test_body_context_refuses_a_stale_citation(tmp_path: Path):
    source = tmp_path / "target.py"
    source.write_text(
        "def wrong():\n"
        "    return 'different'\n\n"
        "def other():\n"
        "    return 'also different'\n"
    )

    assert machine._body_at(tmp_path, f'{source}:2 — "needle",') == ""


def test_body_context_relocates_uniquely_and_is_bounded(tmp_path: Path):
    source = tmp_path / "target.py"
    rows = ["def target():"] + [f"    value_{n} = '{'x' * 120}'" for n in range(90)]
    rows[61] = "    needle = 'needle'"
    rows.append("    return needle")
    source.write_text("\n".join(rows) + "\n")

    body = machine._body_at(tmp_path, f'{source}:2 — "needle = \'needle\'",')

    assert "def target" in body
    assert "needle = 'needle'" in body
    assert len(body) <= machine.BODY_CHAR_LIMIT


def test_body_context_keeps_the_citation_when_one_source_line_exceeds_the_limit(
    tmp_path: Path,
):
    source = tmp_path / "target.py"
    source.write_text(
        "def target():\n    value = '" + ("x" * 10_000) + " UNIQUE_NEEDLE'\n"
    )

    body = machine._body_at(tmp_path, f'{source}:1 — "UNIQUE_NEEDLE",')

    assert "def target" in body
    assert "UNIQUE_NEEDLE" in body
    assert len(body) <= machine.BODY_CHAR_LIMIT


def test_universal_preparation_is_opt_in_and_never_becomes_proof(tmp_path: Path):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    result = machine.drive(
        _order(source), work, tmp_path, "tests", prepare_universal_paths=True
    )

    instruction = result["work"][0]["instruction"]
    assert "normal return" in instruction
    assert "retry" in instruction
    assert "post-validation" in instruction
    assert "preparation is not acceptance evidence" in instruction


def test_reader_map_is_mechanical_and_keeps_builder_conclusions_private(tmp_path: Path):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    _seed_change(work, tmp_path)

    result = machine.drive(_order(source), work, tmp_path, "tests", reader_map=True)

    assert len(result["work"]) == machine.PASSES
    for job in result["work"]:
        instruction = job["instruction"]
        assert "Mechanical starting points" in instruction
        assert "target" in instruction
        assert "PRIVATE BUILDER CONCLUSION" not in instruction
        assert "starting points, not a boundary" in instruction


def test_reader_map_records_neutral_before_image_before_the_builder_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {"command": "tests", "exit_code": 0, "failed": [], "names": []},
    )

    result = machine.drive(_order(source), work, tmp_path, "tests", reader_map=True)

    before = json.loads((work / "build-r1" / "navigation-before.json").read_text())
    assert before["target.py"]["target"]["hash"]
    assert "Citation matches and their enclosing symbols" in result["work"][0]["instruction"]


def test_path_manifest_is_automatic_for_builder_and_blind_readers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {"command": "tests", "exit_code": 0, "failed": [], "names": []},
    )

    builder = machine.drive(_order(source), work, tmp_path, "tests")

    assert "Mechanical structural starting points" in builder["work"][0]["instruction"]
    before = work / "build-r1" / "navigation-before.json"
    assert before.is_file()
    (work / "build-r1" / "change.json").write_text(
        json.dumps(
            {
                "files": ["target.py"],
                "what_changed": "PRIVATE BUILDER CONCLUSION",
                "tests_changed": [],
                "left_alone": "nothing",
            }
        )
    )
    readers = machine.drive(_order(source), work, tmp_path, "tests")

    assert len(readers["work"]) == machine.PASSES
    for job in readers["work"]:
        assert "Structural navigation map" in job["instruction"]
        assert "Changed symbols, derived from the machinery's before-image" in job["instruction"]
        assert "Runnable real-path reproduction" in job["instruction"]
        assert "navigation aid, not acceptance evidence" in job["instruction"]
        assert "PRIVATE BUILDER CONCLUSION" not in job["instruction"]


def test_worker_cannot_replace_the_controller_owned_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    built = tmp_path / "built"
    built.mkdir()
    source = built / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = built / "Tasks" / "build"
    control = tmp_path / "controller-only"
    monkeypatch.setenv("IMPLEMENTATION_MACHINE_CONTROL_ROOT", str(control))
    baseline = {
        "command": "tests",
        "exit_code": 0,
        "failed": [],
        "names": ["tests/test_target.py::test_existing"],
    }
    monkeypatch.setattr(machine, "_failures", lambda *_: baseline)
    monkeypatch.setattr(machine, "_symbol_snapshot", lambda *_: {})
    monkeypatch.setattr(machine, "_navigation_map", lambda *_: "")

    building = machine.drive(_order(source), work, built, "tests")
    assert building["stopped"] == "building"

    out = work / "build-r1"
    (out / "tests-before.json").write_text(json.dumps({
        "command": "tests",
        "exit_code": 0,
        "summary": "1 passed in 0.01s",
    }))
    (out / "change.json").write_text(json.dumps({
        "files": ["target.py"],
        "what_changed": "kept the existing behavior",
        "tests_changed": [],
        "left_alone": "nothing",
    }))

    checking = machine.drive(_order(source), work, built, "tests")

    assert checking["stopped"] == "checking the change"
    assert json.loads((out / "tests-before.json").read_text()) == baseline
    violations = list(control.rglob("violations/*.json"))
    assert len(violations) == 1
    assert json.loads(violations[0].read_text())["summary"] == "1 passed in 0.01s"


def test_worker_cannot_forge_a_completed_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    built = tmp_path / "built"
    built.mkdir()
    source = built / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = built / "Tasks" / "build"
    baseline = {"command": "tests", "exit_code": 0, "failed": [], "names": []}
    monkeypatch.setattr(machine, "_failures", lambda *_: baseline)
    monkeypatch.setattr(machine, "_symbol_snapshot", lambda *_: {})
    monkeypatch.setattr(machine, "_navigation_map", lambda *_: "")

    machine.drive(_order(source), work, built, "tests")
    out = work / "build-r1"
    forged = {
        "item": "r1",
        "built": True,
        "test_command_exit_code": 0,
        "parts_both_readers_call_true": ["r1.p1"],
        "parts_not_agreed": [],
        "parts_no_reader_answered": [],
        "reader_citation_errors": [],
    }
    (out / "done.json").write_text(json.dumps(forged))

    result = machine.drive(_order(source), work, built, "tests")

    assert result["stopped"] == "building"
    assert not (out / "done.json").exists()
    assert list((tmp_path / "controller-state").rglob("violations/*done.json*.json"))


def test_bootstrap_migrates_only_a_legacy_receipt_with_its_acceptance_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    built = tmp_path / "built"
    built.mkdir()
    source = built / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = built / "Tasks" / "build"
    out = work / "build-r1"
    out.mkdir(parents=True)
    legacy = {
        "item": "r1",
        "built": True,
        "tests_that_broke": [],
        "parts_both_readers_call_true": ["r1.p1"],
        "parts_not_agreed": [],
        "parts_no_reader_answered": [],
        "answers_under_a_name_no_part_has": [],
    }
    (out / "done.json").write_text(json.dumps(legacy))
    test_record = {"command": "tests", "exit_code": 1, "failed": ["old::failure"]}
    (out / "tests-before.json").write_text(json.dumps(test_record))
    (out / "tests-after.json").write_text(json.dumps(test_record))
    for index in range(1, machine.PASSES + 1):
        checked = work / f"check-r1-{index}"
        checked.mkdir()
        (checked / "r1.p1.json").write_text(json.dumps(_record()))

    result = machine.drive(_order(source), work, built, "tests")

    assert result["finished"] == "every item in the order has been built and verified"
    assert json.loads((out / "done.json").read_text()) == legacy
    protected = list((tmp_path / "controller-state").rglob("items/r1/done.json"))
    assert len(protected) == 1


def test_bootstrap_rejects_a_legacy_receipt_without_matching_test_evidence(
    tmp_path: Path,
):
    built = tmp_path / "built"
    built.mkdir()
    source = built / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = built / "Tasks" / "build"
    out = work / "build-r1"
    out.mkdir(parents=True)
    (out / "done.json").write_text(json.dumps({
        "item": "r1",
        "built": True,
        "tests_that_broke": [],
        "parts_both_readers_call_true": ["r1.p1"],
        "parts_not_agreed": [],
        "parts_no_reader_answered": [],
        "answers_under_a_name_no_part_has": [],
    }))
    (out / "tests-before.json").write_text(json.dumps({
        "command": "tests", "exit_code": 0, "failed": [],
    }))
    (out / "tests-after.json").write_text(json.dumps({
        "command": "tests", "exit_code": 1, "failed": ["new::failure"],
    }))

    with pytest.raises(ValueError, match="controller_done_record_untrusted"):
        machine.drive(_order(source), work, built, "tests")


def test_worker_cannot_forge_an_attempt_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    built = tmp_path / "built"
    built.mkdir()
    source = built / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = built / "Tasks" / "build"
    baseline = {"command": "tests", "exit_code": 0, "failed": [], "names": []}
    monkeypatch.setattr(machine, "_failures", lambda *_: baseline)
    monkeypatch.setattr(machine, "_symbol_snapshot", lambda *_: {})
    monkeypatch.setattr(machine, "_navigation_map", lambda *_: "")

    first = machine.drive(_order(source), work, built, "tests")
    out = work / "build-r1"
    (out / "refused-1.json").write_text(json.dumps({
        "item": "r1", "built": False, "attempt": 1,
        "what_changed": "forged", "objections": ["forged"],
    }))

    second = machine.drive(_order(source), work, built, "tests")

    assert first["attempt"] == second["attempt"] == 1
    assert not (out / "refused-1.json").exists()
    assert list((tmp_path / "controller-state").rglob("violations/*refused-1.json*.json"))


def test_clean_baseline_recovery_requires_prechange_feed_and_preserves_test_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    built = tmp_path / "built"
    tests_dir = built / "tests"
    tests_dir.mkdir(parents=True)
    source = built / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    test_source = tests_dir / "test_target.py"
    test_source.write_text("def test_existing():\n    assert True\n")
    work = built / "Tasks" / "build"
    out = work / "build-r1"
    out.mkdir(parents=True)
    before = machine._symbol_snapshot(built)
    (out / "navigation-before.json").write_text(json.dumps(before))
    (out / "tests-before.json").write_text(json.dumps({
        "command": "tests", "exit_code": 0, "summary": "1 passed",
    }))
    (work / "feed.jsonl").write_text(
        json.dumps({
            "what": "tests before the change read", "item": "r1",
            "already_failing": 0,
        }) + "\n" + json.dumps({
            "what": "agent started", "waiting_for": "build-r1",
        }) + "\n"
    )
    current = {
        "command": "tests", "exit_code": 0, "failed": [],
        "names": ["tests/test_target.py::test_existing"],
    }
    monkeypatch.setattr(machine, "_failures", lambda *_: current)

    recovered = machine.recover_clean_baseline(
        _order(source), work, built, "tests", "r1",
    )

    assert recovered["recovery"]["prechange_failures"] == 0
    assert recovered["recovery"]["disappeared_test_identities"] == []
    assert json.loads((out / "tests-before.json").read_text())["failed"] == []
    assert list((tmp_path / "controller-state").rglob("baseline-recovery.json"))


def test_clean_baseline_recovery_refuses_a_disappeared_preexisting_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    built = tmp_path / "built"
    tests_dir = built / "tests"
    tests_dir.mkdir(parents=True)
    source = built / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    test_source = tests_dir / "test_target.py"
    test_source.write_text("def test_existing():\n    assert True\n")
    work = built / "Tasks" / "build"
    out = work / "build-r1"
    out.mkdir(parents=True)
    (out / "navigation-before.json").write_text(
        json.dumps(machine._symbol_snapshot(built))
    )
    test_source.write_text("def helper():\n    return True\n")
    (out / "tests-before.json").write_text(json.dumps({
        "command": "tests", "exit_code": 0, "summary": "1 passed",
    }))
    (work / "feed.jsonl").write_text(
        json.dumps({
            "what": "tests before the change read", "item": "r1",
            "already_failing": 0,
        }) + "\n" + json.dumps({
            "what": "agent started", "waiting_for": "build-r1",
        }) + "\n"
    )
    monkeypatch.setattr(machine, "_failures", lambda *_: pytest.fail("must fail first"))

    with pytest.raises(ValueError, match="test_identity_disappeared"):
        machine.recover_clean_baseline(_order(source), work, built, "tests", "r1")


def test_navigation_map_resolves_ambiguous_citations_and_maps_their_consumers(
    tmp_path: Path,
):
    source = tmp_path / "subject.py"
    source.write_text(
        "def first():\n"
        "    marker = [\n"
        "        'one',\n"
        "    ]\n"
        "    return marker\n\n"
        "def second():\n"
        "    marker = [\n"
        "        'two',\n"
        "    ]\n"
        "    return marker\n\n"
        "def consumer():\n"
        "    value = first()\n"
        "    value = normalize(value)\n"
        "    return finalize(value)\n"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_subject.py").write_text(
        "from subject import first\n\n"
        "def test_first():\n"
        "    assert first()\n"
    )
    item = _order(source)["work"][0]
    item["parts"][0]["seen_at"] = f"{source}:99 — marker = ["

    navigation = machine._navigation_map(tmp_path, item)

    assert navigation.count("inside first") == 1
    assert navigation.count("inside second") == 1
    assert "inside consumer calls first" in navigation
    assert "normalize@15" in navigation
    assert "finalize@16" in navigation
    assert "tests/test_subject.py:4 inside test_first calls first" in navigation
    assert len(navigation) <= machine.NAVIGATION_CHAR_LIMIT

    reproduction = machine._reproduction_handoff("uv run pytest", navigation)
    assert "uv run pytest tests/test_subject.py" in reproduction
    assert "real production path" in reproduction
    assert "navigation aid, not acceptance evidence" in reproduction


def test_reader_navigation_derives_changed_symbols_from_neutral_before_image(
    tmp_path: Path,
):
    source = tmp_path / "target.py"
    source.write_text(
        "def target():\n    return 'needle'\n\n"
        "def unchanged():\n    return 'same'\n"
    )
    before = machine._symbol_snapshot(tmp_path)
    source.write_text(
        "def target():\n    return 'changed needle'\n\n"
        "def added():\n    return target()\n\n"
        "def unchanged():\n    return 'same'\n"
    )
    item = _order(source)["work"][0]

    context = machine._reader_context(
        tmp_path, item, ["target.py"], before,
    )

    assert "changed: target.py:1 target" in context
    assert "added: target.py:4 added" in context
    assert "changed: target.py:7 unchanged" not in context
    assert "inside added calls target" in context
    assert "PRIVATE BUILDER CONCLUSION" not in context


def test_navigation_map_clips_at_a_line_boundary_and_says_so():
    lines = ["heading"] + ["x" * 500 for _ in range(100)]

    navigation = machine._bounded_navigation(lines)

    assert len(navigation) <= machine.NAVIGATION_CHAR_LIMIT
    assert navigation.endswith("inspect the source beyond it]")


def test_navigation_index_excludes_tracked_task_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    live = tmp_path / "src" / "live.py"
    snapshot = tmp_path / "Tasks" / "old" / "source-snapshots" / "tree" / "live.py"
    live.parent.mkdir(parents=True)
    snapshot.parent.mkdir(parents=True)
    live.write_text("def live():\n    return True\n")
    snapshot.write_text("def stale():\n    return False\n")
    monkeypatch.setattr(
        machine.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=(
                "src/live.py\0"
                "Tasks/old/source-snapshots/tree/live.py\0"
            ),
        ),
    )

    assert machine._python_files(tmp_path) == [live]


def test_invalid_reader_record_repairs_only_that_seat_without_rebuilding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    one = work / "check-r1-1"
    two = work / "check-r1-2"
    one.mkdir()
    two.mkdir()
    (one / "r1.p1.json").write_text(json.dumps(_record()))
    (two / "wrong.json").write_text(json.dumps(_record("[r1.p1]")))
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {"command": "tests", "exit_code": 0, "failed": [], "names": []},
    )

    result = machine.drive(
        _order(source), work, tmp_path, "tests", repair_reader_records=True
    )

    assert result["stopped"] == "repairing reader records"
    assert len(result["work"]) == 1
    assert Path(result["work"][0]["waiting_for"]).name == "check-r1-2"
    assert one.is_dir()
    assert (out / "change.json").is_file()
    assert not list(out.glob("refused-*.json"))
    assert list(work.glob("check-r1-2-invalid-1"))


def test_second_invalid_delivery_stops_without_consuming_a_build_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    for index in (1, 2):
        checked = work / f"check-r1-{index}"
        checked.mkdir()
        (checked / "answer.json").write_text(
            json.dumps(_record("[r1.p1]" if index == 2 else "r1.p1"))
        )
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {"command": "tests", "exit_code": 0, "failed": [], "names": []},
    )

    first = machine.drive(
        _order(source), work, tmp_path, "tests", repair_reader_records=True
    )
    assert first["stopped"] == "repairing reader records"
    repaired = work / "check-r1-2"
    (repaired / "still-wrong.json").write_text(json.dumps(_record("[r1.p1]")))

    second = machine.drive(
        _order(source), work, tmp_path, "tests", repair_reader_records=True
    )

    assert second["stopped"] == "reader record repair needs a person"
    assert second["work"] == []
    assert (out / "change.json").is_file()
    assert not list(out.glob("refused-*.json"))


def test_captured_universal_counterexample_still_refuses_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Acceleration must preserve the r211 attempt-3/4 kind of substantive no."""

    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    counterexamples = (
        "retry exhaustion writes the restricted phrase into the fallback",
        "post-validation heading insertion reintroduces restricted material",
    )
    for index, looked_at in enumerate(counterexamples, start=1):
        checked = work / f"check-r1-{index}"
        checked.mkdir()
        record = _record(answer="no")
        record["citations"] = []
        record["looked_at"] = looked_at
        (checked / "r1.p1.json").write_text(json.dumps(record))
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {"command": "tests", "exit_code": 0, "failed": [], "names": []},
    )

    result = machine.drive(
        _order(source), work, tmp_path, "tests", with_body=True,
        prepare_universal_paths=True, reader_map=True, repair_reader_records=True,
    )

    assert result["built"] is False
    assert result["parts_not_agreed"] == ["r1.p1"]
    assert result["objections"] == [f"r1.p1: {reason}" for reason in counterexamples]
    assert (out / "refused-1.json").is_file()
    assert not list(work.glob("check-r1-*-invalid-*"))


def test_third_semantic_refusal_persists_the_terminal_owner_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    for attempt in (1, 2):
        (out / f"refused-{attempt}.json").write_text(
            json.dumps(
                {
                    "item": "r1",
                    "built": False,
                    "attempt": attempt,
                    "what_changed": "prior attempt",
                    "objections": ["r1.p1: still false"],
                }
            )
        )
    for index in (1, 2):
        checked = work / f"check-r1-{index}"
        checked.mkdir()
        record = _record(answer="no")
        record["citations"] = []
        record["looked_at"] = "the requirement is still false"
        (checked / "r1.p1.json").write_text(json.dumps(record))
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {"command": "tests", "exit_code": 0, "failed": [], "names": []},
    )

    result = machine.drive(_order(source), work, tmp_path, "tests")
    persisted = json.loads((out / "refused-3.json").read_text())

    assert result["built"] is False
    assert result["attempt"] == machine.ATTEMPTS
    assert result["for_a_person"] == persisted["for_a_person"]


def test_third_changed_nothing_refusal_persists_the_terminal_owner_handoff(
    tmp_path: Path,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = work / "build-r1"
    out.mkdir(parents=True)
    (out / "tests-before.json").write_text(
        json.dumps({"command": "tests", "exit_code": 0, "failed": [], "names": []})
    )
    for attempt in (1, 2):
        (out / f"refused-{attempt}.json").write_text(json.dumps({
            "item": "r1", "built": False, "attempt": attempt,
            "what_changed": "the builder stopped", "objections": ["changed nothing"],
        }))
    (out / "change.json").write_text(json.dumps({
        "files": [], "what_changed": "the tests contradict the requirement",
        "left_alone": "the contradictory test",
    }))

    result = machine.drive(_order(source), work, tmp_path, "tests")
    persisted = json.loads((out / "refused-3.json").read_text())

    assert result["built"] is False
    assert result["for_a_person"] == persisted["for_a_person"]
    assert result["attempts"] == machine.ATTEMPTS


def test_terminal_semantic_refusal_does_not_open_a_fourth_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = work / "build-r1"
    out.mkdir(parents=True)
    (out / "tests-before.json").write_text(
        json.dumps({"command": "tests", "exit_code": 0, "failed": [], "names": []})
    )
    for attempt in range(1, machine.ATTEMPTS + 1):
        receipt = {
            "item": "r1",
            "built": False,
            "attempt": attempt,
            "what_changed": "prior attempt",
            "objections": ["r1.p1: still false"],
        }
        if attempt == machine.ATTEMPTS:
            receipt["for_a_person"] = "The configured attempt limit was reached."
        (out / f"refused-{attempt}.json").write_text(json.dumps(receipt))
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: pytest.fail("terminal resume must not rerun tests"),
    )

    result = machine.drive(_order(source), work, tmp_path, "tests")

    assert result["built"] is False
    assert result["attempt"] == machine.ATTEMPTS
    assert result["for_a_person"] == "The configured attempt limit was reached."
    assert "work" not in result
    assert not (out / "change.json").exists()


def test_authorized_new_ruling_reopens_terminal_and_preserves_stale_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = work / "build-r1"
    out.mkdir(parents=True)
    (out / "tests-before.json").write_text(
        json.dumps({"command": "tests", "exit_code": 0, "failed": [], "names": []})
    )
    for refusal_number in range(1, machine.ATTEMPTS + 1):
        receipt = {
            "item": "r1", "built": False, "attempt": refusal_number,
            "what_changed": "old ruling work", "objections": ["r1.p1: still false"],
        }
        if refusal_number == machine.ATTEMPTS:
            receipt["for_a_person"] = "The configured attempt limit was reached."
        machine._write_controller_record(
            work, "r1", out / f"refused-{refusal_number}.json", receipt,
        )
    (out / "change.json").write_text(json.dumps({"files": ["target.py"]}))
    (out / "navigation-before.json").write_text("{}")
    (out / "tests-after.json").write_text("{}")
    (work / "build-r1-scratch").mkdir()
    (work / "build-r1-scratch" / "old.txt").write_text("old builder")
    for index in (1, 2):
        (work / f"check-r1-{index}").mkdir()
        (work / f"check-r1-{index}" / "old.txt").write_text("old reader")
        (work / f"check-r1-{index}-scratch").mkdir()
    ruling = "Keep the review requirement, but never invent the review outcome."
    (work / "rulings.json").write_text(json.dumps({
        "r1": {"owner_ruling": ruling, "resume_after_terminal": True}
    }))
    monkeypatch.setattr(machine, "_symbol_snapshot", lambda *_: {})
    monkeypatch.setattr(machine, "_navigation_map", lambda *_: "")

    result = machine.drive(_order(source), work, tmp_path, "tests")

    assert result["stopped"] == "building"
    assert result["attempt"] == 1
    assert result["refusal_number"] == 4
    assert ruling in result["work"][0]["instruction"]
    assert sorted(path.name for path in out.glob("refused-*.json")) == [
        "refused-1.json", "refused-2.json", "refused-3.json",
    ]
    history = out / "ruling-history-1"
    assert (history / "change.json").is_file()
    assert (history / "navigation-before.json").is_file()
    assert (history / "tests-before.json").is_file()
    assert (history / "tests-after.json").is_file()
    assert (out / "tests-before.json").is_file()
    assert (history / "build-r1-scratch" / "old.txt").is_file()
    assert (history / "check-r1-1" / "old.txt").is_file()
    assert (history / "check-r1-2" / "old.txt").is_file()
    state = json.loads((out / "ruling-state.json").read_text())
    assert state["refusal_start"] == 3
    assert state["ruling_sha256"] == machine._ruling_sha256({
        "owner_ruling": ruling, "resume_after_terminal": True,
    })


def test_same_ruling_cannot_reopen_a_second_terminal_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = work / "build-r1"
    out.mkdir(parents=True)
    (out / "tests-before.json").write_text(
        json.dumps({"command": "tests", "exit_code": 0, "failed": [], "names": []})
    )
    for refusal_number in range(1, machine.ATTEMPTS + 1):
        (out / f"refused-{refusal_number}.json").write_text(json.dumps({
            "item": "r1", "built": False, "attempt": refusal_number,
            "what_changed": "old ruling work", "objections": ["r1.p1: still false"],
        }))
    ruling = {"owner_ruling": "The new ruling.", "resume_after_terminal": True}
    (work / "rulings.json").write_text(json.dumps({"r1": ruling}))
    monkeypatch.setattr(machine, "_symbol_snapshot", lambda *_: {})
    monkeypatch.setattr(machine, "_navigation_map", lambda *_: "")

    reopened = machine.drive(_order(source), work, tmp_path, "tests")
    assert reopened["attempt"] == 1
    for offset in range(1, machine.ATTEMPTS + 1):
        refusal_number = machine.ATTEMPTS + offset
        receipt = {
            "item": "r1", "built": False, "attempt": offset,
            "refusal_number": refusal_number,
            "ruling_sha256": machine._ruling_sha256(ruling),
            "what_changed": "new ruling work", "objections": ["r1.p1: still false"],
        }
        if offset == machine.ATTEMPTS:
            receipt["for_a_person"] = "Three attempts under this ruling were refused."
        machine._write_controller_record(
            work, "r1", out / f"refused-{refusal_number}.json", receipt,
        )
    monkeypatch.setattr(
        machine, "_failures", lambda *_: pytest.fail("same ruling must stay terminal"),
    )

    result = machine.drive(_order(source), work, tmp_path, "tests")

    assert result["for_a_person"] == "Three attempts under this ruling were refused."
    assert "work" not in result
    assert not (out / "ruling-history-2").exists()


def test_existing_ruling_epoch_refreshes_a_baseline_created_before_the_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = work / "build-r1"
    out.mkdir(parents=True)
    stale = {"command": "tests", "exit_code": 1, "failed": ["old"], "names": ["old"]}
    (out / "tests-before.json").write_text(json.dumps(stale))
    ruling = {"owner_ruling": "The owner settled it.", "resume_after_terminal": True}
    (work / "rulings.json").write_text(json.dumps({"r1": ruling}))
    (out / "ruling-state.json").write_text(json.dumps({
        "ruling_sha256": machine._ruling_sha256(ruling),
        "refusal_start": 3,
        "history": "ruling-history-1",
    }))
    fresh = {"command": "tests", "exit_code": 0, "failed": [], "names": ["fresh"]}
    monkeypatch.setattr(machine, "_failures", lambda *_: fresh)
    monkeypatch.setattr(machine, "_symbol_snapshot", lambda *_: {})
    monkeypatch.setattr(machine, "_navigation_map", lambda *_: "")

    result = machine.drive(_order(source), work, tmp_path, "tests")

    assert result["attempt"] == 1
    assert json.loads((out / "tests-before.json").read_text()) == fresh
    assert json.loads((out / "ruling-history-1" / "tests-before.json").read_text()) == stale
    assert json.loads((out / "ruling-state.json").read_text())["baseline_refreshed"] is True


def test_owner_ruling_reaches_both_blind_reader_packets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    ruling = "Require review, and leave its outcome unchanged until recorded."
    (work / "rulings.json").parent.mkdir()
    (work / "rulings.json").write_text(json.dumps({"r1": ruling}))
    monkeypatch.setattr(
        machine, "_failures",
        lambda *_: {"command": "tests", "exit_code": 0, "failed": [], "names": []},
    )
    monkeypatch.setattr(machine, "_symbol_snapshot", lambda *_: {})
    monkeypatch.setattr(machine, "_navigation_map", lambda *_: "")

    build = machine.drive(_order(source), work, tmp_path, "tests")
    assert ruling in build["work"][0]["instruction"]
    (work / "build-r1" / "change.json").write_text(json.dumps({
        "files": ["target.py"], "what_changed": "PRIVATE BUILDER CONCLUSION",
        "tests_changed": [], "left_alone": "nothing",
    }))

    checking = machine.drive(_order(source), work, tmp_path, "tests")

    assert len(checking["work"]) == machine.PASSES
    for packet in checking["work"]:
        assert ruling in packet["instruction"]
        assert "authoritative meaning of the requirement" in packet["instruction"]
        assert "PRIVATE BUILDER CONCLUSION" not in packet["instruction"]
        assert "one of two independent readers" in packet["instruction"]


def test_test_removal_authorization_does_not_steer_blind_readers(tmp_path: Path):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    _seed_change(work, tmp_path)
    owner_words = "The obsolete test may be removed."
    (work / "rulings.json").write_text(json.dumps({
        "r1": {
            "test_removals": {
                "tests/test_target.py::test_old": {
                    "authorized": True,
                    "owner_ruling": owner_words,
                    "replacement_or_remaining_coverage": "test_new covers the same path.",
                }
            }
        }
    }))

    checking = machine.drive(_order(source), work, tmp_path, "tests")

    assert len(checking["work"]) == machine.PASSES
    assert all(owner_words not in packet["instruction"] for packet in checking["work"])
    assert not (work / "build-r1" / "ruling-state.json").exists()


def test_unattended_loop_stops_on_the_terminal_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    order_path = tmp_path / "order.json"
    order_path.write_text(json.dumps({"work": []}))
    (tmp_path / "work").mkdir()
    calls = 0

    def terminal_drive(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            pytest.fail("the unattended loop asked for work after the terminal refusal")
        return {
            "item": "r1",
            "built": False,
            "attempt": machine.ATTEMPTS,
            "for_a_person": "The configured attempt limit was reached.",
        }

    reported = []
    monkeypatch.setattr(machine, "drive", terminal_drive)
    monkeypatch.setattr(machine, "_say", lambda result: reported.append(result) or 0)

    exit_code = machine.main(
        [
            "--order", str(order_path),
            "--work", str(tmp_path / "work"),
            "--built", str(tmp_path),
            "--tests", "tests",
            "--reader-command", "codex exec",
            "--items", "30",
        ]
    )

    assert exit_code == 0
    assert calls == 1
    assert reported[0]["stopped_at"] == "the configured attempt limit"
    assert reported[0]["last"]["for_a_person"]


def test_empty_builder_delivery_relaunches_without_consuming_an_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {"command": "tests", "exit_code": 0, "failed": [], "names": []},
    )

    first = machine.drive(_order(source), work, tmp_path, "tests")
    second = machine.drive(_order(source), work, tmp_path, "tests")

    assert first["attempt"] == second["attempt"] == 1
    assert first["stopped"] == second["stopped"] == "building"
    assert not list((work / "build-r1").glob("refused-*.json"))


def test_launch_preserves_codex_failure_stream_and_uses_collision_proof_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    worker = tmp_path / "fake_codex.py"
    worker.write_text(
        "import json,sys\n"
        "print(json.dumps({'type':'item.started','item':"
        "{'type':'command_execution','command':'pytest focused.py'}}), flush=True)\n"
        "print(json.dumps({'type':'turn.failed','error':"
        "{'message':'model is temporarily at capacity'}}), flush=True)\n"
        "print('diagnostic on stderr', file=sys.stderr, flush=True)\n"
        "raise SystemExit(1)\n"
    )
    work = tmp_path / "work"
    work.mkdir()
    delivery = tmp_path / "build-r210"
    scratch = tmp_path / "scratch"
    job = machine._packet(
        "make the requirement true", delivery, scratch, False, tmp_path, "tests",
        wants="change.json", owner_approved=True,
    )
    monkeypatch.setattr(
        machine, "validate_reader_command", lambda _command: [sys.executable, str(worker)]
    )

    first = machine._launch([job], "codex exec --json -", tmp_path, work, "1")[0]
    second = machine._launch([job], "codex exec --json -", tmp_path, work, "1")[0]

    assert first["exit_code"] == second["exit_code"] == 1
    assert first["wrote"] == second["wrote"] == 0
    assert first["failure"] == second["failure"] == "model is temporarily at capacity"
    assert first["log"] != second["log"]
    for result in (first, second):
        log = Path(result["log"]).read_text()
        assert '"type": "item.started"' in log
        assert '"type": "turn.failed"' in log
        assert "diagnostic on stderr" in log
    feed = (work / "feed.jsonl").read_text()
    assert "command_execution pytest focused.py" in feed
    assert "model is temporarily at capacity" in feed


def test_test_regression_still_blocks_two_reader_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    for index in (1, 2):
        checked = work / f"check-r1-{index}"
        checked.mkdir()
        (checked / "r1.p1.json").write_text(json.dumps(_record()))
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {
            "command": "tests", "exit_code": 1,
            "failed": ["tests/test_target.py::test_existing"], "names": [],
        },
    )

    result = machine.drive(
        _order(source), work, tmp_path, "tests", with_body=True,
        prepare_universal_paths=True, reader_map=True, repair_reader_records=True,
    )

    assert result["built"] is False
    assert result["parts_both_readers_call_true"] == ["r1.p1"]
    assert result["tests_that_broke"] == ["tests/test_target.py::test_existing"]
    assert (out / "refused-1.json").is_file()


def test_nonzero_test_command_blocks_acceptance_without_parsed_failures(tmp_path: Path):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    for index in (1, 2):
        checked = work / f"check-r1-{index}"
        checked.mkdir()
        (checked / "r1.p1.json").write_text(json.dumps(_record()))

    command = f"{shlex.quote(sys.executable)} -c 'import sys; sys.exit(7)'"
    (out / "tests-before.json").write_text(json.dumps({
        "command": command, "exit_code": 0, "failed": [], "names": [],
    }))
    result = machine.drive(_order(source), work, tmp_path, command)

    assert result["built"] is False
    assert result["test_command_exit_code"] == 7
    assert result["tests_that_broke"] == []
    assert "test command exited 7" in result["objections"]
    assert (out / "refused-1.json").is_file()


@pytest.mark.parametrize(
    ("citation", "message"),
    [
        ({"where": "../outside.py", "line": 1, "text": "outside"}, "outside built repository"),
        ({"where": "target.py", "line": 99, "text": "needle"}, "line 99 does not exist"),
        ({"where": "target.py", "line": 2, "text": "needle"}, "does not exactly match"),
    ],
)
def test_reader_yes_requires_repository_resolved_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, citation: dict, message: str,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    (tmp_path.parent / "outside.py").write_text("outside\n")
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    for index in (1, 2):
        checked = work / f"check-r1-{index}"
        checked.mkdir()
        record = _record()
        record["citations"] = [citation]
        (checked / "r1.p1.json").write_text(json.dumps(record))
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {"command": "tests", "exit_code": 0, "failed": [], "names": []},
    )

    result = machine.drive(_order(source), work, tmp_path, "tests")

    assert result["built"] is False
    assert any(message in error for error in result["reader_citation_errors"])
    assert any(message in objection for objection in result["objections"])
    assert (out / "refused-1.json").is_file()


def _seed_disappeared_test_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    (out / "tests-before.json").write_text(
        json.dumps(
            {
                "command": "tests",
                "exit_code": 0,
                "failed": [],
                "names": ["tests/test_target.py::test_existing"],
            }
        )
    )
    for index in (1, 2):
        checked = work / f"check-r1-{index}"
        checked.mkdir()
        (checked / "r1.p1.json").write_text(json.dumps(_record()))
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {"command": "tests", "exit_code": 0, "failed": [], "names": []},
    )
    return source, work, out


@pytest.mark.parametrize(
    "identity",
    [
        (
            "tests/unit/test_strategy_brief_prompt.py::StrategyBriefPromptHardeningTests::"
            "test_respondent_quote_check_accepts_whole_sentence_and_ignores_nonrespondent_excerpt"
        ),
        (
            "tests/unit/test_platform_decisions.py::ProofClaimClearanceStateTests::"
            "test_explicit_empty_state_survives_recorded_decision_id"
        ),
        (
            "tests/unit/test_strategy_brief_prompt.py::StrategyBriefInputPassthroughTests::"
            "test_gap_return_settlement_receives_policy_candidate_as_supplied"
        ),
    ],
)
def test_disappeared_test_is_returned_to_builder_before_blind_readers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, identity: str,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_target.py").write_text(
        "def test_replacement():\n    assert True\n"
    )
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    tests = f"{shlex.quote(sys.executable)} -m pytest -q"
    (out / "tests-before.json").write_text(
        json.dumps(
            {
                "command": tests,
                "exit_code": 0,
                "failed": [],
                "names": [identity],
            }
        )
    )

    result = machine.drive(_order(source), work, tmp_path, tests)

    assert result["built"] is False
    assert result["stopped"] == "correcting protected test identities before reading"
    assert result["test_removals_needing_owner"] == [identity]
    assert not (work / "check-r1-1").exists()
    assert not (work / "check-r1-2").exists()

    correction = machine.drive(_order(source), work, tmp_path, tests)

    assert correction["stopped"] == "building again"
    assert len(correction["work"]) == 1
    instruction = correction["work"][0]["instruction"]
    assert f"{identity} disappeared before either blind reader" in instruction
    assert "restore that exact collected identity" in instruction


def test_builder_receives_the_exact_protected_test_identity_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    identity = "tests/test_target.py::TargetTests::test_existing"
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {
            "command": "tests", "exit_code": 0, "failed": [], "names": [identity],
        },
    )

    result = machine.drive(_order(source), work, tmp_path, "tests")

    protected = work / "build-r1" / "protected-test-identities.json"
    assert json.loads(protected.read_text()) == {
        "count": 1,
        "identities": [identity],
    }
    instruction = result["work"][0]["instruction"]
    assert str(protected) in instruction
    assert "recorded 1 pre-existing collected test names" in instruction
    assert "checks this before either blind reader starts" in instruction


def test_unchanged_protected_test_identity_proceeds_to_blind_readers(tmp_path: Path):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_target.py").write_text(
        "def test_existing():\n    assert True\n"
    )
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    tests = f"{shlex.quote(sys.executable)} -m pytest -q"
    (out / "tests-before.json").write_text(
        json.dumps(
            {
                "command": tests,
                "exit_code": 0,
                "failed": [],
                "names": ["tests/test_target.py::test_existing"],
            }
        )
    )

    result = machine.drive(_order(source), work, tmp_path, tests)

    assert result["stopped"] == "checking the change"
    assert len(result["work"]) == machine.PASSES
    assert not (out / "refused-1.json").exists()


def test_owner_authorized_test_removal_proceeds_through_the_pre_reader_gate(
    tmp_path: Path,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_target.py").write_text(
        "def test_replacement():\n    assert True\n"
    )
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    tests = f"{shlex.quote(sys.executable)} -m pytest -q"
    identity = "tests/test_target.py::test_existing"
    (out / "tests-before.json").write_text(
        json.dumps(
            {
                "command": tests,
                "exit_code": 0,
                "failed": [],
                "names": [identity],
            }
        )
    )
    (work / "rulings.json").write_text(
        json.dumps(
            {
                "r1": {
                    "test_removals": {
                        identity: {
                            "authorized": True,
                            "owner_ruling": "The obsolete entry point may be removed.",
                            "replacement_or_remaining_coverage": (
                                "test_replacement exercises the replacement path."
                            ),
                        }
                    }
                }
            }
        )
    )
    for index in (1, 2):
        checked = work / f"check-r1-{index}"
        checked.mkdir()
        (checked / "r1.p1.json").write_text(json.dumps(_record()))

    result = machine.drive(_order(source), work, tmp_path, tests)

    assert result["built"] is True
    assert result["approved_test_removals"] == [identity]
    assert result["test_removals_needing_owner"] == []


def test_pre_reader_identity_collection_is_not_repeated_after_readers_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    work = tmp_path / "work"
    out = _seed_change(work, tmp_path)
    identity = "tests/test_target.py::test_existing"
    (out / "tests-before.json").write_text(
        json.dumps(
            {
                "command": "tests",
                "exit_code": 0,
                "failed": [],
                "names": [identity],
            }
        )
    )
    for index in (1, 2):
        checked = work / f"check-r1-{index}"
        checked.mkdir()
        (checked / "r1.p1.json").write_text(json.dumps(_record()))
    monkeypatch.setattr(
        machine,
        "_test_inventory",
        lambda *_: pytest.fail("pre-reader inventory must not repeat after readers start"),
    )
    monkeypatch.setattr(
        machine,
        "_failures",
        lambda *_: {
            "command": "tests", "exit_code": 0, "failed": [], "names": [identity],
        },
    )

    result = machine.drive(_order(source), work, tmp_path, "tests")

    assert result["built"] is True


def test_disappeared_test_blocks_acceptance_without_exact_owner_ruling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source, work, out = _seed_disappeared_test_case(tmp_path, monkeypatch)

    result = machine.drive(_order(source), work, tmp_path, "tests")

    assert result["built"] is False
    assert result["test_removals_needing_owner"] == [
        "tests/test_target.py::test_existing"
    ]
    assert any(
        "tests/test_target.py::test_existing disappeared" in objection
        for objection in result["objections"]
    )
    assert (out / "refused-1.json").is_file()


@pytest.mark.parametrize(
    "authorization",
    [
        {
            "tests/test_other.py::test_other": {
                "authorized": True,
                "owner_ruling": "Remove the obsolete other test.",
                "replacement_or_remaining_coverage": "Covered by test_replacement.",
            }
        },
        {
            "tests/test_target.py::test_existing": {
                "authorized": True,
                "owner_ruling": "Remove this obsolete test.",
                "replacement_or_remaining_coverage": "",
            }
        },
    ],
)
def test_disappeared_test_requires_exact_identity_and_coverage_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, authorization: dict,
):
    source, work, _ = _seed_disappeared_test_case(tmp_path, monkeypatch)
    (work / "rulings.json").write_text(
        json.dumps({"r1": {"test_removals": authorization}})
    )

    result = machine.drive(_order(source), work, tmp_path, "tests")

    assert result["built"] is False
    assert result["test_removals_needing_owner"] == [
        "tests/test_target.py::test_existing"
    ]


def test_exact_owner_ruling_can_authorize_disappeared_test_with_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source, work, out = _seed_disappeared_test_case(tmp_path, monkeypatch)
    (work / "rulings.json").write_text(
        json.dumps(
            {
                "r1": {
                    "test_removals": {
                        "tests/test_target.py::test_existing": {
                            "authorized": True,
                            "owner_ruling": "The old entry-point test may be removed.",
                            "replacement_or_remaining_coverage": (
                                "tests/test_target.py::test_replacement covers the same path."
                            ),
                        }
                    }
                }
            }
        )
    )

    result = machine.drive(_order(source), work, tmp_path, "tests")

    assert result["built"] is True
    assert result["test_removals_needing_owner"] == []
    assert result["approved_test_removals"] == [
        "tests/test_target.py::test_existing"
    ]
    assert (out / "done.json").is_file()


def test_default_drive_keeps_opt_in_experiments_and_unapproved_authority_out(
    tmp_path: Path,
):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    result = machine.drive(_order(source), tmp_path / "work", tmp_path, "tests")

    instruction = result["work"][0]["instruction"]
    assert "normal return" not in instruction
    assert "Mechanical structural starting points" in instruction
    assert "The owner explicitly approved this Implementation Machinery run" not in instruction


def test_worker_packet_prechunks_stable_directives_and_repository_context(tmp_path: Path):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")

    result = machine.drive(_order(source), tmp_path / "work", tmp_path, "uv run pytest")

    instruction = result["work"][0]["instruction"]
    stable = instruction.index("## Stable worker directives")
    repository = instruction.index("## Repository context")
    item = instruction.index("## Item task")
    assert stable < repository < item
    assert f"Repository root: {tmp_path}" in instruction
    assert "Full test command: uv run pytest" in instruction
    assert "Do not go and read a working agreement" in instruction
    assert "Output directory:" in instruction
    assert "Scratch directory:" in instruction


def test_owner_approval_is_relayed_as_a_bounded_worker_envelope(tmp_path: Path):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")

    result = machine.drive(
        _order(source), tmp_path / "work", tmp_path, "tests", owner_approved=True,
    )

    instruction = result["work"][0]["instruction"]
    assert "The owner explicitly approved this Implementation Machinery run" in instruction
    assert "do not stop to ask again" in instruction
    assert "It does not authorize unrelated edits, commits, pushes, deployments" in instruction


def test_launch_routes_uv_cache_to_the_workers_own_scratch(tmp_path: Path):
    built = tmp_path / "built"
    work = tmp_path / "work"
    out = work / "answer"
    scratch = work / "answer-scratch"
    built.mkdir()
    reader = tmp_path / "reader.py"
    reader.write_text(
        "import json, os, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).mkdir(parents=True, exist_ok=True)\n"
        "pathlib.Path(sys.argv[1], 'change.json').write_text("
        "json.dumps({'uv_cache': os.environ['UV_CACHE_DIR'], "
        "'uv_no_sync': os.environ['UV_NO_SYNC']}))\n"
    )
    job = machine._packet(
        "read", out, scratch, blind=False, built=built, tests="tests",
        wants="change.json",
    )

    result = machine._launch(
        [job], f"{shlex.quote(sys.executable)} {shlex.quote(str(reader))} "
        f"{shlex.quote(str(out))}", built, work, "cache",
    )

    delivered = json.loads((out / "change.json").read_text())
    assert result[0]["wrote"] == 1
    assert Path(delivered["uv_cache"]) == scratch / "uv-cache"
    assert delivered["uv_no_sync"] == "1"
