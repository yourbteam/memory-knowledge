"""Focused contracts for Implementation Machinery acceleration paths."""
from __future__ import annotations

import importlib.util
import json
import shlex
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
        "citations": [{"where": "/tmp/target.py", "line": 1, "text": "needle"}],
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


def test_default_drive_keeps_acceleration_out_of_existing_packets(tmp_path: Path):
    source = tmp_path / "target.py"
    source.write_text("def target():\n    return 'needle'\n")
    result = machine.drive(_order(source), tmp_path / "work", tmp_path, "tests")

    instruction = result["work"][0]["instruction"]
    assert "normal return" not in instruction
    assert "Mechanical starting points" not in instruction
    assert "The owner explicitly approved this Implementation Machinery run" not in instruction


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
    job = machine._packet("read", out, scratch, blind=False, wants="change.json")

    result = machine._launch(
        [job], f"{shlex.quote(sys.executable)} {shlex.quote(str(reader))} "
        f"{shlex.quote(str(out))}", built, work, "cache",
    )

    delivered = json.loads((out / "change.json").read_text())
    assert result[0]["wrote"] == 1
    assert Path(delivered["uv_cache"]) == scratch / "uv-cache"
    assert delivered["uv_no_sync"] == "1"
