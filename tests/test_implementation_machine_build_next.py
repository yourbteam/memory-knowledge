"""Focused contracts for Implementation Machinery acceleration paths."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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
