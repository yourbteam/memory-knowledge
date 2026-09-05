#!/usr/bin/env python3
"""Atom 17 champion (approach already-resolves-is-a-start-check): apply to one source tree root.

Atom 16 refused "introduced field already resolves; declare it without 'introduced'" at every stage.
That is a declaration error only when a new run starts. Once a run is started and the canonical
module gains the field, a resolved introduced field is the healthy end state: load-run, status,
change-surface and record-promotion accept it. CM-B13, 2026-09-05: round-5 atom D could not be
promoted through the door Atom 16 opened.
"""
from __future__ import annotations

import sys
from pathlib import Path


def patch(path: Path, pairs: list[tuple[str, str]]) -> None:
    text = path.read_text()
    for old, new in pairs:
        assert text.count(old) == 1, (path.name, text.count(old), old[:70])
        text = text.replace(old, new)
    path.write_text(text)


def main(root: Path) -> int:
    controller = root / "skills/atom-building-machinery/scripts/atom_controller.py"
    patch(controller, [
        ('''    elif pending and len(segments) == 1:
        raise AtomError(
            stage,
            f"introduced field {field!r} already resolves at {segments[0]!r}; declare it without 'introduced'",
        )''',
         '''    elif pending and len(segments) == 1 and stage == "start":
        # Atom 17 (2026-09-05): only a new start may not declare an existing field as introduced. A
        # started run whose introduced field has since landed in the canonical module keeps loading.
        raise AtomError(
            stage,
            f"introduced field {field!r} already resolves at {segments[0]!r}; declare it without 'introduced'",
        )'''),
        ('''        elif pending:
            raise AtomError(
                stage,
                f"introduced field {field!r} already resolves at {segments[1]!r}; declare it without 'introduced'",
            )''',
         '''        elif pending and stage == "start":
            raise AtomError(
                stage,
                f"introduced field {field!r} already resolves at {segments[1]!r}; declare it without 'introduced'",
            )'''),
    ])
    skill = root / "skills/atom-building-machinery/SKILL.md"
    text = skill.read_text()
    marker = "declare it without 'introduced'"
    if marker in text and "keeps loading" not in text:
        idx = text.index(marker)
        end = text.index("\n", idx)
        text = text[:end] + (" Once the run is started, the canonical module gaining the field is the expected end state: the run keeps loading and promotes; that refusal is a start-time declaration check only.") + text[end:]
        skill.write_text(text)
    tests = root / "tests/test_atom_building_machinery.py"
    text = tests.read_text()
    anchor = "def test_introduced_field_that_already_exists_or_is_misspelled_is_refused("
    new_test = '''def test_a_run_with_an_introduced_field_loads_once_the_module_carries_it(
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


'''
    assert anchor in text and "loads_once_the_module_carries_it" not in text
    tests.write_text(text.replace(anchor, new_test + anchor, 1))
    print(f"champion applied to {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve()))
