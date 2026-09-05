#!/usr/bin/env python3
"""Atom 19 champion (approach report-rule-per-run): apply to one source tree root.

Every round of the roadmap work re-based its own measure ("of the 21 version-5 cells, how many
closed", "of the 5 version-6 cells, how many closed"), so no report could be subtracted from the
one before it and the delivered page's real trend — 22, 15, 9, 25, 12 located defects across its
critiqued versions — was never printed by anything. `trend` gives the critique machinery that one
frozen number: for each run passed, it counts located defects by the exact rule the report route
already uses (agreement-defect cells plus owner-resolved cells ruled revise or reject), orders the
runs by the version their bound page names, prints each count with its delta from the previous
comparable run, lists a run whose reading or owner queue is unfinished without comparing it, and
refuses runs of another deliverable or two runs of one version, naming the runs.
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


TREND_BLOCK = r'''

# ----------------------------------------------------------------------------------------------
# Atom 19 (2026-09-05): `trend` — one frozen measure across the completed runs of one deliverable.
# Each run's located defects are counted by the rule the report route already uses; runs are
# ordered by the version their bound page names; a run whose reading or owner queue is unfinished
# is listed but never compared; runs of another deliverable, or two runs of one version, refuse.
# ----------------------------------------------------------------------------------------------
LOCATED_DEFECT_RULE = "agreement-defect cells plus owner-resolved cells whose ruling is revise or reject"
PAGE_VERSION = re.compile(r"_v(\d+)\.[A-Za-z0-9]+$")


def _is_located_defect(cell: dict[str, Any]) -> bool:
    return cell.get("outcome") == "agreement-defect" or cell.get("resolved_verdict") in {"reject", "revise"}


def trend_entry(work: Path) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    status = matrix_status(work)
    page_name = Path(manifest["page"]["path"]).name
    match = PAGE_VERSION.search(page_name)
    cells = matrix["cells"]
    reasons = []
    if status["unjudged_count"]:
        reasons.append(f"{status['unjudged_count']} cells unjudged")
    if status["owner_queue_count"]:
        reasons.append(f"{status['owner_queue_count']} owner questions open")
    return {
        "work": str(work.resolve()),
        "page": page_name,
        "page_sha256": manifest["page"]["sha256"],
        "version": int(match.group(1)) if match else None,
        "payload_key": manifest["payload"]["key"],
        "state": Path(manifest["payload"]["state_path"]).name,
        "status": status["status"],
        "comparable": not reasons,
        "not_comparable_because": "; ".join(reasons) or None,
        "cell_count": len(cells),
        "agreed_defects": sum(cell.get("outcome") == "agreement-defect" for cell in cells),
        "owner_resolved_defects": sum(
            cell.get("outcome") == "owner-resolved" and cell.get("resolved_verdict") in {"reject", "revise"}
            for cell in cells
        ),
        "located_defects": sum(_is_located_defect(cell) for cell in cells),
        "open_owner_questions": status["owner_queue_count"],
        "unjudged_cells": status["unjudged_count"],
        "recording_refusals": status["refused_count"],
        "delta": None,
    }


def trend(works: list[Path]) -> dict[str, Any]:
    if not works:
        raise Refusal("trend requires at least one --work run directory.")
    entries = [trend_entry(work) for work in works]
    first = entries[0]
    for entry in entries[1:]:
        if entry["payload_key"] != first["payload_key"]:
            raise Refusal(
                f"trend refused: run {first['work']} bound payload key {first['payload_key']!r} while run "
                f"{entry['work']} bound {entry['payload_key']!r}; pass runs of one deliverable only "
                f"(drop {entry['work']} or trend it separately)."
            )
    for entry in entries:
        if entry["version"] is None:
            raise Refusal(
                f"trend refused: run {entry['work']} bound page {entry['page']!r}, which names no version "
                "(a suffix such as _v6.md); trend orders runs by that version, so pass runs whose bound page names its version."
            )
    by_version: dict[int, dict[str, Any]] = {}
    for entry in entries:
        other = by_version.get(entry["version"])
        if other is not None:
            raise Refusal(
                f"trend refused: runs {other['work']} and {entry['work']} both bound page version "
                f"{entry['version']} ({other['page']}, {entry['page']}); a trend has one run per version, so pass one of them."
            )
        by_version[entry["version"]] = entry
    ordered = [by_version[version] for version in sorted(by_version)]
    previous = None
    for entry in ordered:
        if entry["comparable"]:
            entry["delta"] = None if previous is None else entry["located_defects"] - previous["located_defects"]
            previous = entry
    comparable = [entry for entry in ordered if entry["comparable"]]
    deltas = [entry["delta"] for entry in comparable[1:]]
    if len(comparable) < 2:
        direction = None
    elif all(delta == 0 for delta in deltas):
        direction = "flat"
    elif all(delta <= 0 for delta in deltas):
        direction = "falling"
    elif all(delta >= 0 for delta in deltas):
        direction = "rising"
    else:
        direction = "mixed"
    return {
        "status": "trend",
        "deliverable": first["payload_key"],
        "measure": LOCATED_DEFECT_RULE,
        "order": "by the version named in each run's bound page",
        "runs": ordered,
        "comparable_versions": [entry["version"] for entry in comparable],
        "located_defects_by_version": {str(entry["version"]): entry["located_defects"] for entry in comparable},
        "deltas": deltas,
        "direction": direction,
        "first": (
            {"version": comparable[0]["version"], "located_defects": comparable[0]["located_defects"]}
            if comparable else None
        ),
        "latest": (
            {"version": comparable[-1]["version"], "located_defects": comparable[-1]["located_defects"]}
            if comparable else None
        ),
        "not_comparable": [
            {"version": entry["version"], "because": entry["not_comparable_because"]}
            for entry in ordered if not entry["comparable"]
        ],
    }


def safe_extract(archive: Path, destination: Path) -> None:'''

TEST_BLOCK = r'''

FROZEN_TREND = ROOT / "Tasks/critique-machinery/atom-19/frozen-real"


def test_trend_orders_real_btm_runs_by_page_version_with_deltas_and_refuses_mixed_or_repeated_versions() -> None:
    module = load_module()
    runs = [FROZEN_TREND / name for name in ("btm-v5-run", "btm-v1-run", "btm-v6-run", "btm-v2-run", "btm-v3-run")]
    result = module.trend(runs)
    assert [entry["version"] for entry in result["runs"]] == [1, 2, 3, 5, 6]
    assert [entry["located_defects"] for entry in result["runs"]] == [22, 15, 9, 25, 12]
    for entry in result["runs"]:
        report = module.reporting_route(Path(entry["work"]), "report")
        assert entry["located_defects"] == report["located_defects"]
        assert entry["comparable"] is True
    assert result["deltas"] == [-7, -6, 16, -13]
    assert result["direction"] == "mixed"
    assert result["deliverable"] == "context.up.cd_s_002.tactical_roadmap"
    partial = module.trend([FROZEN_TREND / "btm-v7-run-partial", FROZEN_TREND / "btm-v6-run"])
    assert [entry["version"] for entry in partial["runs"]] == [6, 7]
    assert partial["runs"][1]["comparable"] is False
    assert partial["runs"][1]["not_comparable_because"] == "21 owner questions open"
    assert partial["runs"][1]["agreed_defects"] == 10
    assert partial["runs"][1]["delta"] is None
    assert partial["direction"] is None
    with pytest.raises(module.Refusal) as mixed:
        module.trend([FROZEN_TREND / "btm-v6-run", FROZEN_TREND / "one-pager-run"])
    assert "context.up.cd_s_002.strategy_one_pager" in str(mixed.value)
    assert "one-pager-run" in str(mixed.value)
    with pytest.raises(module.Refusal) as repeated:
        module.trend([FROZEN_TREND / "btm-v6-run", FROZEN_TREND / "btm-v6-consistency-run-partial"])
    assert "both bound page version 6" in str(repeated.value)
'''

SKILL_COMMAND = (
    "python3 scripts/critique.py located --work <work> --only disputed\n"
    "python3 scripts/critique.py trend --work <run-v1> --work <run-v2> --work <run-v3>\n"
)

SKILL_PARAGRAPH = """
`trend` is the one measure that survives across versions. Given completed runs of one deliverable,
it counts each run's located defects by the exact rule the report uses — agreement-defect cells plus
owner-resolved cells ruled revise or reject — orders the runs by the version their bound page names,
and prints each count with its delta from the previous comparable run and the direction of the
whole series. A run whose reading or owner queue is unfinished is listed with its reason and never
compared. Runs of another deliverable, a page that names no version, or two runs of one version
refuse, naming the runs. It spends no reader call and reads only the runs' own records; a project's
goal store reads this command rather than composing a per-round number.
"""


def main(root: Path) -> None:
    script = root / "skills/critique-machinery/scripts/critique.py"
    patch(
        script,
        [
            ("\n\ndef safe_extract(archive: Path, destination: Path) -> None:", TREND_BLOCK),
            (
                '    located_parser.add_argument("--only", choices=("disputed", "defects", "all"), default="disputed")\n',
                '    located_parser.add_argument("--only", choices=("disputed", "defects", "all"), default="disputed")\n'
                '    trend_parser = sub.add_parser(\n'
                '        "trend", help="located defects per completed run of one deliverable, ordered by page version, with deltas"\n'
                '    )\n'
                '    trend_parser.add_argument("--work", action="append", required=True)\n',
            ),
            (
                '        elif args.command == "located":\n            print(located(Path(args.work), args.only), end="")\n            return 0\n',
                '        elif args.command == "located":\n            print(located(Path(args.work), args.only), end="")\n            return 0\n'
                '        elif args.command == "trend":\n            result = trend([Path(work) for work in args.work])\n',
            ),
        ],
    )
    tests = root / "tests/test_critique_machinery.py"
    tests.write_text(tests.read_text().rstrip("\n") + "\n" + TEST_BLOCK)
    skill = root / "skills/critique-machinery/SKILL.md"
    patch(
        skill,
        [
            ("python3 scripts/critique.py located --work <work> --only disputed\n", SKILL_COMMAND),
            (
                "missing or invalid evidence refuses instead of reconstructing words.\n",
                "missing or invalid evidence refuses instead of reconstructing words.\n" + SKILL_PARAGRAPH,
            ),
        ],
    )
    print(f"champion applied to {root}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
