#!/usr/bin/env python3
"""Atom 16 champion (approach introduced-resolved-at-promotion): apply to one source tree root.

An atom may mark a contract-surface field `"introduced": true`. At start the field's parent must
resolve and its leaf must not exist yet; at record-promotion the leaf must resolve because the
canonical module now carries it. Every other declaration keeps today's exact resolution.
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
        ('CONTRACT_FIELD_FIELDS = {"field", "shape", "shape_source"}\n',
         'CONTRACT_FIELD_FIELDS = {"field", "shape", "shape_source"}\n'
         '#: Atom 16 (2026-09-05): a field the atom itself introduces. Its parent must resolve at start,\n'
         '#: its leaf must not exist yet, and the leaf must resolve at record-promotion.\n'
         'CONTRACT_FIELD_OPTIONAL_FIELDS = {"introduced"}\n'),
        ('''def _resolve_contract_field(
    item: dict[str, str],
    deliverable: str,
    repository_root: Path,
    label: str,
    stage: str,
) -> dict[str, str]:
    field = _nonempty(item["field"], f"{label}.field", stage)''',
         '''def _resolve_contract_field(
    item: dict[str, Any],
    deliverable: str,
    repository_root: Path,
    label: str,
    stage: str,
    *,
    require_introduced_resolved: bool = False,
) -> dict[str, Any]:
    field = _nonempty(item["field"], f"{label}.field", stage)
    introduced = bool(item.get("introduced"))
    pending = introduced and not require_introduced_resolved'''),
        ('''    if segments[0] not in section_keys:
        raise AtomError(
            stage,
            f"field {field!r} does not resolve at {segments[0]!r}; available deliverable keys are {sorted(section_keys)!r}",
        )
    if len(segments) > 1:
        nested = _available_nested_keys(collections, segments[0])
        if segments[1] not in nested:
            raise AtomError(
                stage,
                f"field {field!r} does not resolve at {segments[1]!r}; available keys are {sorted(nested)!r}",
            )''',
         '''    if segments[0] not in section_keys:
        if pending and len(segments) == 1:
            pass  # a top-level field the atom introduces; its parent is the deliverable itself
        elif introduced:
            raise AtomError(
                stage,
                f"introduced field {field!r} still does not resolve at {segments[0]!r} at {stage}; the "
                f"canonical module must carry it before the promotion receipt is recorded; available "
                f"deliverable keys are {sorted(section_keys)!r}",
            )
        else:
            raise AtomError(
                stage,
                f"field {field!r} does not resolve at {segments[0]!r}; available deliverable keys are {sorted(section_keys)!r}",
            )
    elif pending and len(segments) == 1:
        raise AtomError(
            stage,
            f"introduced field {field!r} already resolves at {segments[0]!r}; declare it without 'introduced'",
        )
    if len(segments) > 1:
        nested = _available_nested_keys(collections, segments[0])
        if segments[1] not in nested:
            if pending:
                pass  # the leaf the atom introduces; its parent resolved above
            elif introduced:
                raise AtomError(
                    stage,
                    f"introduced field {field!r} still does not resolve at {segments[1]!r} at {stage}; the "
                    f"canonical module must carry it before the promotion receipt is recorded; available "
                    f"keys are {sorted(nested)!r}",
                )
            else:
                raise AtomError(
                    stage,
                    f"field {field!r} does not resolve at {segments[1]!r}; available keys are {sorted(nested)!r}",
                )
        elif pending:
            raise AtomError(
                stage,
                f"introduced field {field!r} already resolves at {segments[1]!r}; declare it without 'introduced'",
            )'''),
        ('''    if shape not in {"enum", "pinned-string"}:
        if constant not in collections:
            raise AtomError(stage, f"field {field!r} shape {shape} requires a named string field collection")
        target = segments[-1]
        if target not in collections[constant] and segments[0] not in collections[constant]:
            raise AtomError(
                stage,
                f"field {field!r} is not named by shape constant {constant!r}; "
                f"that constant provides {collections[constant]!r}",
            )
    return {"field": field, "shape": shape, "shape_source": f"{source_path_text}::{constant}"}''',
         '''    if shape not in {"enum", "pinned-string"}:
        if constant not in collections:
            raise AtomError(stage, f"field {field!r} shape {shape} requires a named string field collection")
        target = segments[-1]
        if not pending and target not in collections[constant] and segments[0] not in collections[constant]:
            raise AtomError(
                stage,
                f"field {field!r} is not named by shape constant {constant!r}; "
                f"that constant provides {collections[constant]!r}",
            )
    resolved: dict[str, Any] = {"field": field, "shape": shape, "shape_source": f"{source_path_text}::{constant}"}
    if introduced:
        resolved["introduced"] = True
    return resolved'''),
        ('''    allow_missing_prose_waiver: bool = False,
    allow_legacy_prose_waiver: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if type(value) is not dict:
        raise AtomError(stage, "contract_surface is not one object")''',
         '''    allow_missing_prose_waiver: bool = False,
    allow_legacy_prose_waiver: bool = False,
    require_introduced_resolved: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if type(value) is not dict:
        raise AtomError(stage, "contract_surface is not one object")'''),
        ('''        item = _exact(raw, f"contract_surface.fields[{index}]", CONTRACT_FIELD_FIELDS, stage)
        minimally_valid = {
            "field": _nonempty(item["field"], f"contract_surface.fields[{index}].field", stage),
            "shape": item["shape"],
            "shape_source": _nonempty(
                item["shape_source"], f"contract_surface.fields[{index}].shape_source", stage
            ),
        }''',
         '''        item = _exact_with_optional(
            raw, f"contract_surface.fields[{index}]", CONTRACT_FIELD_FIELDS, CONTRACT_FIELD_OPTIONAL_FIELDS, stage
        )
        minimally_valid: dict[str, Any] = {
            "field": _nonempty(item["field"], f"contract_surface.fields[{index}].field", stage),
            "shape": item["shape"],
            "shape_source": _nonempty(
                item["shape_source"], f"contract_surface.fields[{index}].shape_source", stage
            ),
        }
        if "introduced" in item:
            if item["introduced"] is not True:
                raise AtomError(
                    stage,
                    f"contract_surface.fields[{index}].introduced is {item['introduced']!r}; write true for a "
                    "field this atom introduces, or omit it",
                )
            minimally_valid["introduced"] = True'''),
        ('''            fields.append(
                _resolve_contract_field(
                    minimally_valid, deliverable, repository_root,
                    f"contract_surface.fields[{index}]", stage,
                )
            )''',
         '''            fields.append(
                _resolve_contract_field(
                    minimally_valid, deliverable, repository_root,
                    f"contract_surface.fields[{index}]", stage,
                    require_introduced_resolved=require_introduced_resolved,
                )
            )'''),
        ('''    allow_missing_prose_waiver: bool = False,
    allow_legacy_prose_waiver: bool = False,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise AtomError(stage, "atom request is not one object")''',
         '''    allow_missing_prose_waiver: bool = False,
    allow_legacy_prose_waiver: bool = False,
    require_introduced_resolved: bool = False,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise AtomError(stage, "atom request is not one object")'''),
        ('''        surface, waiver = _validate_contract_surface(
            request["contract_surface"], request.get("prose_waiver"), repository_root, stage,
            allow_missing_prose_waiver=allow_missing_prose_waiver,
            allow_legacy_prose_waiver=allow_legacy_prose_waiver,
        )''',
         '''        surface, waiver = _validate_contract_surface(
            request["contract_surface"], request.get("prose_waiver"), repository_root, stage,
            allow_missing_prose_waiver=allow_missing_prose_waiver,
            allow_legacy_prose_waiver=allow_legacy_prose_waiver,
            require_introduced_resolved=require_introduced_resolved,
        )'''),
        ('''    if state["stage"] != "promotion":
        raise AtomError("record-promotion", f"current stage is {state['stage']!r}; require 'promotion'")
    request = _request(run)
    baseline = _baseline(run, request)''',
         '''    if state["stage"] != "promotion":
        raise AtomError("record-promotion", f"current stage is {state['stage']!r}; require 'promotion'")
    request = _request(run)
    _require_introduced_fields_resolved(run)
    baseline = _baseline(run, request)'''),
        ('''def _within(path: str, allowed: list[str]) -> bool:''',
         '''def _require_introduced_fields_resolved(run: Path) -> None:
    """Atom 16: a field the atom introduced must resolve in the repository before promotion."""
    raw = _load(run / "inputs" / "atom-request.json", "stored atom request", "record-promotion")
    surface = raw.get("contract_surface") if type(raw) is dict else None
    fields = surface.get("fields") if type(surface) is dict else None
    if not fields or not any(type(f) is dict and f.get("introduced") for f in fields):
        return
    records, _ = _read_ledger(run)
    repository_root = Path(_nonempty(records[0]["payload"].get("repository_root"), "atom-started repository_root", "record-promotion"))
    _validate_request(
        raw,
        repository_root=repository_root,
        stage="record-promotion",
        allow_legacy_prose_waiver=True,
        require_introduced_resolved=True,
    )


def _within(path: str, allowed: list[str]) -> bool:'''),
    ])
    skill = root / "skills/atom-building-machinery/SKILL.md"
    patch(skill, [
        ('''  `repository/path.py::CONSTANT`; shapes are `list`, `object`, `enum`, `integer`,
  `pinned-string`, or `prose`.
''',
         '''  `repository/path.py::CONSTANT`; shapes are `list`, `object`, `enum`, `integer`,
  `pinned-string`, or `prose`. A field the atom itself adds carries `"introduced": true`: at
  `start` its parent must resolve and the leaf must not exist yet (an existing leaf is refused
  with "declare it without 'introduced'"); `record-promotion` refuses until the canonical module
  carries the leaf. A misspelled field without `introduced` is still refused at `start` with the
  available keys.
'''),
    ])
    tests = root / "tests/test_atom_building_machinery.py"
    text = tests.read_text()
    anchor = "def test_validation_surface_misspelling_names_available_keys("
    assert text.count(anchor) == 1
    new_tests = '''def test_introduced_field_starts_and_must_resolve_before_promotion(
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


'''
    tests.write_text(text.replace(anchor, new_tests + anchor))
    print("champion applied to", root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
