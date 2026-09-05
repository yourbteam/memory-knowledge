#!/usr/bin/env python3
"""Atom 18 champion (approach code-owned-lens-both-seats): apply to one source tree root.

The critique machinery reads one unit at a time, so it cannot see a page that contradicts itself
across units. Round 5 made the roadmap's spans, stages and months structured fields, so those
cross-unit facts are checkable by code: a `payload-consistency` lens whose two seats are code,
filled by `consistency --work` from the bound payload. Both seats record the same verdict and the
same located line, so the lens never raises an owner question; `read-run` never sends it to a
reader; a unit no declared check reads, or a run opened without a deliverable profile, records the
lens as not applicable with its reason.
"""
from __future__ import annotations

import sys
from pathlib import Path


def patch(path: Path, pairs: list[tuple[str, str]]) -> None:
    text = path.read_text()
    for old, new in pairs:
        assert text.count(old) == 1, (path.name, text.count(old), old[:80])
        text = text.replace(old, new)
    path.write_text(text)


CHECKS_BLOCK = r'''

# ----------------------------------------------------------------------------------------------
# Atom 18 (2026-09-05): the code-owned payload-consistency lens. Each check reads one unit's text
# against the bound payload and returns facts — one per compared thing, each with the unit line it
# sits on — or None when the page or payload carries nothing the check reads.
# ----------------------------------------------------------------------------------------------
ROADMAP_PHASE_ORDER = ("Pre-Seed", "Launch", "Sustain", "Amplify")
DEPLOY_MONTH = re.compile(r"deploy from Month (\d+)")
ADVOCACY_CARD = re.compile(r"advoca", re.IGNORECASE)


def _phase_span_of(months_text: Any) -> tuple[int, int]:
    numbers = [int(number) for number in re.findall(r"\d+", str(months_text))]
    return (numbers[0], numbers[-1]) if numbers else (1, 12)


def _phases_spanned(payload: dict[str, Any], low: int, high: int) -> str:
    spans = {
        str(row.get("phase")): _phase_span_of(row.get("months"))
        for row in payload.get("phases") or []
        if isinstance(row, dict)
    }
    phases = [
        phase for phase in ROADMAP_PHASE_ORDER
        if phase in spans and any(spans[phase][0] <= month <= spans[phase][1] for month in range(low, high + 1))
    ]
    if len(phases) == len(ROADMAP_PHASE_ORDER):
        return "all phases"
    return " → ".join(phases)


def _spanned_cards(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        card for card in payload.get("activation_cards") or []
        if isinstance(card, dict)
        and type(card.get("month")) is int
        and type(card.get("last_month")) is int
    ]


def _line_number(lines: list[str], predicate: Any) -> int | None:
    for number, line in enumerate(lines, 1):
        if predicate(line):
            return number
    return None


def _fact(check: str, subject: str, line: int, expected: str, actual: str) -> dict[str, Any]:
    return {
        "check": check,
        "subject": subject,
        "line": line,
        "expected": expected,
        "actual": actual,
        "verdict": "clear" if expected == actual else "defect",
    }


def _check_map_cell_vs_span(unit: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    cards = _spanned_cards(payload)
    if not cards:
        return None
    lines = unit["text"].splitlines()
    facts = []
    for card in cards:
        name = str(card["name"])
        number = _line_number(lines, lambda line: line.startswith("| ") and f"| {name} |" in line)
        expected = _phases_spanned(payload, card["month"], card["last_month"])
        if number is None:
            facts.append(_fact("map-cell-vs-span", name, 1, expected, "no map row names this card"))
            continue
        actual = lines[number - 1].strip().strip("|").split("|")[-1].strip()
        facts.append(_fact("map-cell-vs-span", name, number, expected, actual))
    return facts


def _check_stage_months_cover_spans(unit: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    order = payload.get("proof_building_order")
    if not isinstance(order, list) or not order:
        return None
    cards = {
        str(card.get("name")): card
        for card in payload.get("activation_cards") or []
        if isinstance(card, dict)
    }
    lines = unit["text"].splitlines()
    facts = []
    for stage in order:
        if not isinstance(stage, dict):
            continue
        label = str(stage.get("stage"))
        months = set(month for month in stage.get("months") or [] if type(month) is int)
        number = _line_number(lines, lambda line: line.startswith(f"**{label}**")) or 1
        for name in stage.get("cards") or []:
            card = cards.get(str(name))
            if card is None or type(card.get("month")) is not int:
                continue
            last = card.get("last_month") if type(card.get("last_month")) is int else card["month"]
            span = set(range(card["month"], last + 1))
            lacking = sorted(span - months)
            facts.append(_fact(
                "stage-months-cover-card-span", f"{label} / {name}", number,
                f"stage months cover Months {card['month']}-{last}",
                "covered" if not lacking else f"stage months lack {lacking}",
            ) if lacking else _fact(
                "stage-months-cover-card-span", f"{label} / {name}", number,
                f"stage months cover Months {card['month']}-{last}",
                f"stage months cover Months {card['month']}-{last}",
            ))
    return facts or None


def _check_calendar_names_span_months(unit: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    cards = [card for card in _spanned_cards(payload) if card["last_month"] > card["month"]]
    if not cards:
        return None
    lines = unit["text"].splitlines()
    facts = []
    for card in cards:
        name = str(card["name"])
        for month in range(card["month"], card["last_month"] + 1):
            number = _line_number(lines, lambda line: line.startswith(f"| Month {month} |"))
            if number is None:
                facts.append(_fact("calendar-names-card-in-span-month", f"{name} / Month {month}", 1,
                                   f"a Month {month} row names the card", "no such calendar row"))
                continue
            present = name.lower() in lines[number - 1].lower()
            facts.append(_fact("calendar-names-card-in-span-month", f"{name} / Month {month}", number,
                               f"the Month {month} row names the card",
                               f"the Month {month} row names the card" if present else f"the Month {month} row does not name the card"))
    return facts


def _check_loop_deploy_month(unit: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    lines = unit["text"].splitlines()
    number = _line_number(lines, lambda line: DEPLOY_MONTH.search(line) is not None)
    advocacy = next(
        (card for card in payload.get("activation_cards") or []
         if isinstance(card, dict) and ADVOCACY_CARD.search(f"{card.get('name')} {card.get('idea')}")),
        None,
    )
    if number is None or advocacy is None or type(advocacy.get("month")) is not int:
        return None
    stated = int(DEPLOY_MONTH.search(lines[number - 1]).group(1))
    return [_fact("loop-deploy-month-is-equipping-card-month", str(advocacy.get("name")), number,
                  f"deploy from Month {advocacy['month']}", f"deploy from Month {stated}")]


def _check_widening_month_in_launch(unit: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    rollout = payload.get("rollout") if isinstance(payload.get("rollout"), dict) else {}
    month = rollout.get("widening_month")
    if type(month) is not int:
        return None
    lines = unit["text"].splitlines()
    number = _line_number(lines, lambda line: line.startswith("**Then widen")) or 1
    launch = next((row for row in payload.get("phases") or [] if isinstance(row, dict) and row.get("phase") == "Launch"), None)
    low, high = _phase_span_of(launch.get("months")) if launch else (1, 12)
    inside = low <= month <= high
    return [_fact("widening-month-inside-launch-span", "rollout", number,
                  f"widening month inside Launch Months {low}-{high}",
                  f"widening month inside Launch Months {low}-{high}" if inside else f"widening Month {month} outside Launch Months {low}-{high}")]


#: Which units of which deliverable the code-owned lens reads, by the unit's page heading.
DELIVERABLE_CONSISTENCY_CHECKS: dict[str, dict[str, tuple[Any, ...]]] = {
    "tactical_roadmap": {
        "The activation map": (_check_map_cell_vs_span,),
        "The proof-building order": (_check_stage_months_cover_spans,),
        "The twelve-month calendar": (_check_calendar_names_span_months,),
        "The always-on loop": (_check_loop_deploy_month,),
        "The rollout": (_check_widening_month_in_launch,),
    },
}


def reader_lenses(unit_cells: list[dict[str, Any]], seat: str) -> list[str]:
    """The lenses a blind reader is asked for one unit: never the code-owned lens."""
    return [
        cell["lens"] for cell in unit_cells
        if cell.get("status") != "not-applicable" and seat not in cell["readers"] and cell["lens"] != CODE_LENS
    ]


def run_consistency(work: Path) -> dict[str, Any]:
    """Fill every payload-consistency cell from the bound payload, both seats by code."""
    manifest, matrix = load_matrix(work)
    deliverable = manifest.get("deliverable")
    checks = DELIVERABLE_CONSISTENCY_CHECKS.get(deliverable) if isinstance(deliverable, str) else None
    if not checks:
        raise Refusal(
            "consistency has nothing to read: the run was opened without a deliverable profile that declares "
            "checks, and its payload-consistency cells are already recorded as not applicable."
        )
    bound = manifest["payload"]
    state_path = Path(bound["state_path"])
    if digest_file(state_path) != bound["state_sha256"]:
        raise Refusal(f"consistency refused: the bound state {state_path} changed since the run was opened.")
    payload = lookup(json.loads(state_path.read_text(encoding="utf-8")), bound["key"])
    if digest_bytes(canonical(payload)) != bound["value_sha256"]:
        raise Refusal("consistency refused: the bound payload value differs from the opened run's record.")
    code_cells = [cell for cell in matrix["cells"] if cell["lens"] == CODE_LENS]
    if any(cell.get("readers") for cell in code_cells):
        raise Refusal("consistency already recorded for this run; open a new run instead of replacing evidence.")
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    recorded, not_applicable, defects = [], [], []
    for cell in code_cells:
        if cell.get("status") == "not-applicable":
            continue
        unit = units[cell["unit_id"]]
        functions = checks.get(unit["label"], ())
        facts: list[dict[str, Any]] = []
        applicable = False
        for function in functions:
            result = function(unit, payload)
            if result is None:
                continue
            applicable = True
            facts.extend(result)
        if not applicable:
            reason = (
                "no declared check reads this unit" if not functions
                else "the page or payload carries no field this unit's check reads"
            )
            cell.update({
                "status": "not-applicable",
                "outcome": "not-applicable",
                "consistency_state": {"state": "no-check", "reason": reason, "strategy": CONSISTENCY_STRATEGY},
            })
            not_applicable.append(cell["cell_id"])
            continue
        lines = unit["text"].splitlines()
        failed = [fact for fact in facts if fact["verdict"] == "defect"]
        if failed:
            verdict = "revise"
            start = min(fact["line"] for fact in failed)
            end = max(fact["line"] for fact in failed)
            quote = lines[start - 1]
        else:
            verdict = "clear"
            start = end = next((number for number, line in enumerate(lines, 1) if len(collapsed(line)) >= 25), 1)
            quote = lines[start - 1]
        for seat in READER_SEATS:
            batch_id = f"code-{cell['unit_id']}"
            evidence_root = work / "reader-evidence" / batch_id / seat / "attempt-001"
            evidence_root.mkdir(parents=True, exist_ok=True)
            response = {
                "schema_version": SCHEMA_VERSION,
                "strategy": CONSISTENCY_STRATEGY,
                "judgments": [{"lens": CODE_LENS, "verdict": verdict, "start_line": start, "end_line": end}],
                "facts": facts,
            }
            response_bytes = canonical(response)
            (evidence_root / "reader-response.json").write_bytes(response_bytes)
            intake = {
                "schema_version": SCHEMA_VERSION,
                "request_id": f"{batch_id}::{seat}",
                "batch_id": batch_id,
                "seat": seat,
                "attempt": 1,
                "outcome": "valid",
                "lenses": [CODE_LENS],
                "evidence_path": str(evidence_root),
                "reply_bytes": len(response_bytes),
                "reply_sha256": digest_bytes(response_bytes),
                "exit_code": 0,
                "strategy": CODE_SEAT_STRATEGY,
            }
            _apply_reader_claim(work, manifest, cell, seat, verdict, quote, intake=intake)
        cell["consistency_facts"] = facts
        recorded.append(cell["cell_id"])
        if failed:
            defects.append(cell["cell_id"])
    (work / "matrix.json").write_bytes(canonical(matrix))
    return {
        "status": "recorded",
        "strategy": CONSISTENCY_STRATEGY,
        "deliverable": deliverable,
        "recorded": recorded,
        "defects": defects,
        "not_applicable": not_applicable,
    }
'''


def main(root: Path) -> int:
    script = root / "skills/critique-machinery/scripts/critique.py"
    patch(script, [
        ('''    "benchmark-vs-reference",
    "upstream-trace",
)
TOKEN = re.compile''',
         '''    "benchmark-vs-reference",
    "upstream-trace",
    "payload-consistency",
)
#: Atom 18 (2026-09-05): the one lens whose two seats are code, filled from the bound payload.
CODE_LENS = "payload-consistency"
CODE_SEAT_STRATEGY = "code-owned-payload-consistency"
CONSISTENCY_STRATEGY = "bound-payload-versus-page"
#: Runs opened before Atom 18 carry the seven reader lenses; they stay readable in that shape.
LEGACY_LENSES = tuple(lens for lens in LENSES if lens != CODE_LENS)
TOKEN = re.compile'''),
        ('''def build_matrix(manifest: dict[str, Any]) -> dict[str, Any]:
    declaration = manifest.get("benchmark_reference")''',
         '''def build_matrix(manifest: dict[str, Any], lenses: tuple[str, ...] | list[str] | None = None) -> dict[str, Any]:
    lenses = tuple(lenses or LENSES)
    declaration = manifest.get("benchmark_reference")'''),
        ('''    cells = []
    for unit in manifest["units"]:
        for lens in LENSES:
            cell = {''',
         '''    cells = []
    for unit in manifest["units"]:
        for lens in lenses:
            cell = {'''),
        ('''        "unit_manifest_sha256": digest_bytes(canonical(manifest)),
        "lenses": list(LENSES),
        "cells": cells,''',
         '''        "unit_manifest_sha256": digest_bytes(canonical(manifest)),
        "lenses": list(lenses),
        "cells": cells,'''),
        ('''    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    expected = build_matrix(manifest)
    if matrix.get("unit_manifest_sha256") != expected["unit_manifest_sha256"]:''',
         '''    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    stored_lenses = tuple(matrix.get("lenses") or ())
    if stored_lenses not in {tuple(LENSES), LEGACY_LENSES}:
        raise Refusal(
            f"matrix {matrix_path} declares lenses {list(stored_lenses)!r}; a run carries either the current "
            f"{list(LENSES)!r} or the pre-Atom-18 {list(LEGACY_LENSES)!r}. Open a new run instead of replacing matrix structure."
        )
    expected = build_matrix(manifest, lenses=stored_lenses)
    if matrix.get("unit_manifest_sha256") != expected["unit_manifest_sha256"]:'''),
        ('''    if actual_ids != expected_ids or matrix.get("lenses") != list(LENSES):
        raise Refusal(''',
         '''    if actual_ids != expected_ids:
        raise Refusal('''),
        ('''            if lens == "benchmark-vs-reference" and no_reference:''',
         '''            if lens == CODE_LENS:
                cell["reader_strategy"] = CODE_SEAT_STRATEGY
                if manifest.get("deliverable") not in DELIVERABLE_CONSISTENCY_CHECKS:
                    cell.update(
                        {
                            "status": "not-applicable",
                            "outcome": "not-applicable",
                            "consistency_state": {
                                "state": "no-profile",
                                "reason": "the run was opened without a deliverable profile that declares consistency checks",
                                "strategy": CONSISTENCY_STRATEGY,
                            },
                        }
                    )
            if lens == "benchmark-vs-reference" and no_reference:'''),
        ('''    upstream_sources: list[tuple[str, Path, str]] | None = None,
    no_upstream: str | None = None,
) -> tuple[str, dict[str, Any]]:
    repo_for(work)''',
         '''    upstream_sources: list[tuple[str, Path, str]] | None = None,
    no_upstream: str | None = None,
    deliverable: str | None = None,
) -> tuple[str, dict[str, Any]]:
    repo_for(work)'''),
        ('''    manifest["upstream_sources"] = upstream
    destination = work / "unit-manifest.json"''',
         '''    manifest["upstream_sources"] = upstream
    if deliverable is not None:
        manifest["deliverable"] = deliverable
    destination = work / "unit-manifest.json"'''),
        ('''            lenses = [
                cell["lens"] for cell in unit_cells
                if cell.get("status") != "not-applicable" and seat not in cell["readers"]
            ]
            if lenses:
                jobs.append((unit, seat, lenses))''',
         '''            lenses = reader_lenses(unit_cells, seat)
            if lenses:
                jobs.append((unit, seat, lenses))'''),
        ('''    cell = matches[0]
    if cell.get("status") == "not-applicable":
        return cell
    if cell.get("readers"):
        raise Refusal(f"cell {cell_id!r} already has reader evidence; open a new run instead of replacing it.")
    unit = next(unit for unit in manifest["units"] if unit["unit_id"] == cell["unit_id"])''',
         '''    cell = matches[0]
    if cell.get("status") == "not-applicable":
        return cell
    if cell["lens"] == CODE_LENS:
        raise Refusal(
            f"cell {cell_id!r} belongs to the code-owned {CODE_LENS} lens; run consistency --work, never a reader."
        )
    if cell.get("readers"):
        raise Refusal(f"cell {cell_id!r} already has reader evidence; open a new run instead of replacing it.")
    unit = next(unit for unit in manifest["units"] if unit["unit_id"] == cell["unit_id"])'''),
        ('''        if cell.get("upstream_trace"):
            lines.extend([f"- upstream `{cell['upstream_trace']['source_id']}`: {cell['upstream_trace']['quote']}"])
        if cell.get("benchmark"):''',
         '''        for fact in cell.get("consistency_facts", []):
            if fact.get("verdict") == "defect":
                lines.append(
                    f"- code check `{fact['check']}` on {fact['subject']} (unit line {fact['line']}): "
                    f"expected {fact['expected']}; page says {fact['actual']}"
                )
        if cell.get("upstream_trace"):
            lines.extend([f"- upstream `{cell['upstream_trace']['source_id']}`: {cell['upstream_trace']['quote']}"])
        if cell.get("benchmark"):'''),
        ('''def split_payload(value: str, key: str | None) -> tuple[Path, str]:''',
         CHECKS_BLOCK + '''

def split_payload(value: str, key: str | None) -> tuple[Path, str]:'''),
        ('''    read_run_parser = sub.add_parser("read-run", help="resume blind readers across every unread matrix cell")
    read_run_parser.add_argument("--work", required=True)''',
         '''    read_run_parser = sub.add_parser("read-run", help="resume blind readers across every unread matrix cell")
    read_run_parser.add_argument("--work", required=True)
    consistency_parser = sub.add_parser(
        "consistency", help="fill the code-owned payload-consistency lens from the bound payload"
    )
    consistency_parser.add_argument("--work", required=True)'''),
        ('''                upstream_sources=upstream_sources,
                no_upstream=no_upstream,
            )
            result = {
                "status": status,''',
         '''                upstream_sources=upstream_sources,
                no_upstream=no_upstream,
                deliverable=args.deliverable if derived else None,
            )
            result = {
                "status": status,'''),
        ('''        elif args.command == "read-run":
            result = read_run(Path(args.work))''',
         '''        elif args.command == "read-run":
            result = read_run(Path(args.work))
        elif args.command == "consistency":
            result = run_consistency(Path(args.work))'''),
    ])
    skill = root / "skills/critique-machinery/SKILL.md"
    text = skill.read_text()
    assert "payload-consistency" not in text
    addition = '''## The code-owned consistency lens

The eighth lens, `payload-consistency`, has no reader. For a deliverable opened with
`--from-run --deliverable`, run

```bash
python3 scripts/critique.py consistency --work <work>
```

after `open` and before `read-run`. Code reads the bound payload against the page and fills both
seats of that lens on every unit a declared check reads: a located `revise` where the page
contradicts the payload (a map cell against a card's span, a stage's months against the spans of
the cards it names, the calendar rows against a span, the loop's deployment month against the
equipping card, the widening month against the Launch span), `clear` where it does not, and
`not-applicable` with its reason where no check reads the unit or the page carries no field the
check reads. A run opened with explicit `--payload` flags records the lens as not applicable
because no profile declares checks. Both seats are code and always agree, so the lens never raises
an owner question; `read-run` never sends it to a reader, and `read-cell` refuses it. The evidence
is the same shape as a reader's — a response with the lens, verdict and unit lines under
`reader-evidence/code-<unit>/` — plus every compared fact, and the findings document prints each
contradicted fact under its cell. A page that contradicts itself across units was invisible to the
unit-by-unit seats: on 2026-09-05 both seats cleared a B Team map whose Senior craft story series
read "Sustain" while the card ran Months 6 to 12; this lens locates five such rows on that page.

'''
    marker = "## Installed client model boundary"
    if marker in text:
        skill.write_text(text.replace(marker, addition + marker, 1))
    else:
        skill.write_text(text.rstrip("\n") + "\n\n" + addition.rstrip("\n") + "\n")
    tests = root / "tests/test_critique_machinery.py"
    text = tests.read_text()
    anchor = "def test_reply_intake_has_five_exclusive_actionable_outcomes() -> None:"
    assert anchor in text and "payload_consistency" not in text
    new_tests = '''FROZEN_ATOM_18 = ROOT / "Tasks/critique-machinery/atom-18/frozen-real"


def _open_frozen_roadmap(module, tmp_path: Path, page: str, state: str, name: str):
    repo = tmp_path / name
    (repo / ".git").mkdir(parents=True)
    state_path, key, upstream_sources, _derived = module.derive_open_inputs(FROZEN_ATOM_18 / state, "tactical_roadmap")
    work = repo / "Tasks/run"
    module.open_run(
        FROZEN_ATOM_18 / page, state_path, key, work, no_reference=NO_REFERENCE,
        upstream_sources=upstream_sources, deliverable="tactical_roadmap",
    )
    return work


def test_payload_consistency_lens_locates_cross_unit_contradictions_by_code(tmp_path: Path) -> None:
    """Atom 18 (2026-09-05): both blind seats cleared the B Team version 6 map while five of its cells
    contradicted the cards' spans; the code-owned lens files them as located agreement defects."""
    module = load_module()
    work = _open_frozen_roadmap(module, tmp_path, "btm-v6-page.md", "btm-v6-state.json", "btm")
    manifest, matrix = module.load_matrix(work)
    assert manifest["deliverable"] == "tactical_roadmap"
    code_cells = [cell for cell in matrix["cells"] if cell["lens"] == module.CODE_LENS]
    assert all(cell["reader_strategy"] == module.CODE_SEAT_STRATEGY and cell["status"] == "unjudged" for cell in code_cells)
    unit_cells = [cell for cell in matrix["cells"] if cell["unit_id"] == code_cells[0]["unit_id"]]
    assert module.CODE_LENS not in module.reader_lenses(unit_cells, "reader-1")

    result = module.run_consistency(work)
    assert result["status"] == "recorded"
    labels = {unit["unit_id"]: unit["label"] for unit in manifest["units"]}
    _manifest, matrix = module.load_matrix(work)
    by_label = {labels[cell["unit_id"]]: cell for cell in matrix["cells"] if cell["lens"] == module.CODE_LENS}
    map_cell = by_label["The activation map"]
    assert map_cell["outcome"] == "agreement-defect"
    defective = sorted(fact["subject"] for fact in map_cell["consistency_facts"] if fact["verdict"] == "defect")
    assert defective == sorted([
        "Public identity and proof lock", "Partner proof pack", "Senior craft story series",
        "Earned validation outreach", "Employee advocacy push",
    ])
    for label in ("The proof-building order", "The twelve-month calendar", "The always-on loop", "The rollout"):
        assert by_label[label]["outcome"] == "agreement-clear", label
    others = [cell for label, cell in by_label.items() if label not in {
        "The activation map", "The proof-building order", "The twelve-month calendar", "The always-on loop", "The rollout"}]
    assert others and all(cell["status"] == "not-applicable" and cell["consistency_state"]["state"] == "no-check" for cell in others)
    assert module.owner_queue(work)["open_count"] == 0
    located = module.located(work, "defects")
    assert "| Senior craft story series |" in located and "payload-consistency" in located
    with pytest.raises(module.Refusal):
        module.run_consistency(work)
    with pytest.raises(module.Refusal):
        module.read_cell(work, map_cell["cell_id"])


def test_payload_consistency_is_not_applicable_without_profile_or_span_fields(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "explicit"
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks/run"
    module.open_run(
        FROZEN_ATOM_18 / "btm-v6-page.md", FROZEN_ATOM_18 / "btm-v6-state.json",
        "context.up.cd_s_002.tactical_roadmap", work, no_reference=NO_REFERENCE, no_upstream=NO_UPSTREAM,
    )
    _manifest, matrix = module.load_matrix(work)
    code_cells = [cell for cell in matrix["cells"] if cell["lens"] == module.CODE_LENS]
    assert code_cells and all(
        cell["status"] == "not-applicable" and cell["consistency_state"]["state"] == "no-profile" for cell in code_cells
    )
    with pytest.raises(module.Refusal):
        module.run_consistency(work)

    old = _open_frozen_roadmap(module, tmp_path, "btm-v5-page.from-state.md", "btm-v5-state.json", "v5")
    result = module.run_consistency(old)
    assert result["recorded"] == [] and result["defects"] == []
    _manifest, matrix = module.load_matrix(old)
    assert all(
        cell["status"] == "not-applicable" and cell["consistency_state"]["state"] == "no-check"
        for cell in matrix["cells"] if cell["lens"] == module.CODE_LENS
    )


'''
    text = text.replace(anchor, new_tests + anchor, 1)
    for old_pin, new_pin in (
        ('    assert opening["not_applicable_count"] == 50\n    assert opening["benchmark_no_reference_count"] == 25',
         '    assert opening["not_applicable_count"] == 75  # 25 no-reference, 25 no-upstream, 25 no-profile (Atom 18)\n    assert opening["benchmark_no_reference_count"] == 25'),
        ('    assert opening["cell_count"] == 175\n    assert opening["unjudged_count"] == 150',
         '    assert opening["cell_count"] == 200  # eight lenses since Atom 18; the code lens is not applicable here\n    assert opening["unjudged_count"] == 150'),
        ('    assert opening["not_applicable_count"] == 25\n    assert opening["benchmark_no_reference_count"] == 25\n',
         '    assert opening["not_applicable_count"] == 50  # 25 no-reference plus 25 no-profile (Atom 18)\n    assert opening["benchmark_no_reference_count"] == 25\n'),
        ('    assert result["not_applicable_count"] == 25\n    assert all("benchmark-vs-reference" not in lenses for lenses in calls)\n',
         '    assert result["not_applicable_count"] == 50  # 25 no-reference plus 25 no-profile (Atom 18)\n    assert all("benchmark-vs-reference" not in lenses for lenses in calls)\n'),
    ):
        assert text.count(old_pin) == 1, old_pin[:60]
        text = text.replace(old_pin, new_pin)
    tests.write_text(text)
    print(f"champion applied to {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve()))
