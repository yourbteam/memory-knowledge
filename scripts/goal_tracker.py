#!/usr/bin/env python3
"""The goal a repository is being worked toward, the KPIs it is judged by, and every reading.

Why this exists. On 2026-08-06 the goal changed in conversation -- "make the harness reliable so
the output docs it produces can be sent to UP" -- while the number still being reported came from
a string hardcoded inside a per-project reporting script. Nothing declared the goal, so nothing
could check that the report matched it, and the reported figure had moved 303 -> 302 -> 303 on
identical bytes the same morning. Kamen: "this yo yo that you are reporting now up and down
depletes the whole purpose of tracking progress and makes you look completely stupid."

What this preserves, and why each part is here rather than in a note:

* **Every goal, never overwritten.** A goal is superseded, with the reason and the timestamp, and
  the old one keeps its KPIs and its readings. A goal that can be edited in place cannot be
  audited, and the previous goal's history is what says whether the work was ever converging.
* **KPIs owned by the goal that needs them.** A KPI carries the exact command that produces it and
  the artifact that command reads, so a number is obtained, never composed. When the goal changes
  the KPIs go with it, which is what makes "not comparable" a fact the file states rather than a
  claim in prose.
* **Findings, not only totals.** Each reading stores the items that failed and what failed about
  them. A total says the work moved; the items say what the harness actually did. Kamen: "I expect
  checked and grounded findings if the harness is working."
* **The delta, computed here.** "Change since last measured" is derived from the two most recent
  readings of the same KPI under the same goal. Nothing types it.

How it is called. `set` takes no arguments at all: it interviews through `script_intake`, the same
typed intake the sequence controller uses, which refuses fields that ask for argv, flags or JSON.
That is deliberate -- the failure mode being designed out is not a wrong goal, it is a wrong
invocation. `measure` runs the KPI's own declared command. `report` renders the three lines. `check`
is what a gate calls to refuse a report that was typed rather than obtained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts import script_intake
except ModuleNotFoundError:  # direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import script_intake  # type: ignore[no-redef]


SCHEMA_VERSION = 1
STORE_RELATIVE = Path(".goal") / "goal.json"


# --------------------------------------------------------------------------------------
# The store
# --------------------------------------------------------------------------------------


def store_path(repo: Path) -> Path:
    return repo / STORE_RELATIVE


def load(repo: Path) -> dict[str, Any]:
    path = store_path(repo)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "repo": str(repo), "goals": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(
            f"{path} declares schema_version {data.get('schema_version')!r}; this script "
            f"writes {SCHEMA_VERSION}. Migrate the file rather than letting two shapes coexist."
        )
    return data


def save(repo: Path, data: dict[str, Any]) -> Path:
    path = store_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def current_goal(data: dict[str, Any]) -> dict[str, Any] | None:
    """The one goal in force. A superseded goal keeps everything it recorded."""

    live = [goal for goal in data.get("goals", []) if not goal.get("superseded_at")]
    return live[-1] if live else None


def _now(clock: Any = None) -> str:
    return (clock or (lambda: datetime.now(timezone.utc)))().isoformat()


# --------------------------------------------------------------------------------------
# Declaring a goal — zero-argument intake
# --------------------------------------------------------------------------------------


GOAL_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        {
            "id": "statement",
            "prompt": "The goal, in the words of the person who set it",
            "response_format": "One sentence naming the outcome, not the activity.",
            "example": (
                "make the harness reliable so the output docs it produces can be sent to UP"
            ),
            "constraints": (
                "Quote the person who set it. Do not restate it in the system's vocabulary."
            ),
            "type": "text",
            "required": True,
        },
        {
            "id": "set_by",
            "prompt": "Who set this goal",
            "response_format": "One name.",
            "example": "Kamen",
            "constraints": "The person, not the tool that recorded it.",
            "type": "string",
            "required": True,
        },
        {
            "id": "supersede_reason",
            "prompt": "Why the goal in force is being replaced",
            "response_format": "One sentence. Answer 'none' when this is the first goal.",
            "example": "the previous goal was met and the work moved to document quality",
            "constraints": (
                "Say what stopped holding about the old goal. 'none' is accepted only when no "
                "goal is in force."
            ),
            "type": "string",
            "required": True,
        },
        {
            "id": "kpis",
            "prompt": "The KPIs this goal is judged by",
            "response_format": "One KPI per entry.",
            "example": "sendable-documents",
            "constraints": (
                "Each KPI must be answerable by a checked-in script. A KPI nobody can re-run is "
                "an opinion with a number on it."
            ),
            "type": "object_list",
            "required": True,
            "item_fields": [
                {
                    "id": "id",
                    "prompt": "Short name for this KPI",
                    "response_format": "Lowercase words joined by hyphens.",
                    "example": "sendable-documents",
                    "constraints": "Stable across readings; it is how two readings are compared.",
                    "type": "string",
                    "required": True,
                },
                {
                    "id": "question",
                    "prompt": "The question this KPI answers, in plain words",
                    "response_format": "One sentence a person outside the work could check.",
                    "example": "how many documents a client could receive, of documents produced",
                    "constraints": (
                        "Plain words. This sentence is what appears on the report's GOAL line."
                    ),
                    "type": "text",
                    "required": True,
                },
                {
                    "id": "producer",
                    "prompt": "The checked-in script that produces this number",
                    "response_format": "One repository-relative path.",
                    "example": "scripts/measure_sendable_documents.py",
                    "constraints": (
                        "The file must exist and be tracked by git, so the number can be "
                        "obtained again by anyone. A number with no producer is not a KPI."
                    ),
                    "type": "path",
                    "required": True,
                },
                {
                    "id": "deterministic",
                    "prompt": "Does this producer give the same answer twice on the same input",
                    "response_format": "yes or no.",
                    "example": "yes",
                    "constraints": (
                        "Answer no when any part of the number comes from a model's judgement. "
                        "A KPI that is not deterministic is recorded as such rather than trusted."
                    ),
                    "type": "boolean",
                    "required": True,
                },
                {
                    "id": "direction",
                    "prompt": "Which way is progress",
                    "response_format": "up or down.",
                    "example": "up",
                    "constraints": "up when a larger number is better; down when smaller is.",
                    "type": "choice",
                    "choices": ["up", "down"],
                    "required": True,
                },
            ],
        },
    ],
}


def set_goal(repo: Path, answers: dict[str, Any], *, clock: Any = None) -> dict[str, Any]:
    """Record a new goal, superseding the one in force and keeping everything it recorded."""

    data = load(repo)
    stamp = _now(clock)
    live = current_goal(data)
    if live is not None:
        reason = str(answers.get("supersede_reason") or "").strip()
        if not reason or reason.lower() == "none":
            raise SystemExit(
                f"goal {live['id']!r} is in force; replacing it needs a reason. Re-run and "
                f"answer the supersede question with why it no longer holds."
            )
        live["superseded_at"] = stamp
        live["superseded_reason"] = reason
    for kpi in answers["kpis"]:
        producer = repo / str(kpi["producer"])
        if not producer.is_file():
            # `exists()` was not enough: an intake defect that shifted the answers by one
            # recorded a producer of "." on 2026-08-06, and a directory exists.
            raise SystemExit(
                f"KPI {kpi['id']!r} names producer {kpi['producer']!r}, which is not a file "
                f"under {repo}. Name the script that prints the number; a KPI whose producer "
                f"cannot be run is an opinion with a number on it."
            )
    goal = {
        "id": f"g{len(data['goals']) + 1}",
        "statement": str(answers["statement"]).strip(),
        "set_by": str(answers["set_by"]).strip(),
        "set_at": stamp,
        "kpis": [
            {
                "id": str(kpi["id"]).strip(),
                "question": str(kpi["question"]).strip(),
                "producer": str(kpi["producer"]).strip(),
                "deterministic": bool(kpi["deterministic"]),
                "direction": str(kpi["direction"]).strip(),
            }
            for kpi in answers["kpis"]
        ],
        "measurements": [],
    }
    data["goals"].append(goal)
    save(repo, data)
    return goal


# --------------------------------------------------------------------------------------
# Taking a reading
# --------------------------------------------------------------------------------------


def measure(repo: Path, kpi_id: str, *, runner: Any = None, clock: Any = None) -> dict[str, Any]:
    """Run the KPI's own producer and append what it returned, findings and all."""

    data = load(repo)
    goal = current_goal(data)
    if goal is None:
        raise SystemExit(
            f"no goal is in force for {repo}. Run `goal_tracker.py set` before measuring; "
            f"a number with no goal cannot say whether anything moved."
        )
    kpis = {kpi["id"]: kpi for kpi in goal["kpis"]}
    if kpi_id not in kpis:
        raise SystemExit(
            f"goal {goal['id']!r} has no KPI {kpi_id!r}. It declares: "
            f"{', '.join(sorted(kpis)) or '(none)'}."
        )
    kpi = kpis[kpi_id]
    run = runner or _run_producer
    payload, raw = run(repo, kpi["producer"])
    for field in ("value", "total"):
        if not isinstance(payload.get(field), int):
            raise SystemExit(
                f"{kpi['producer']} returned {field}={payload.get(field)!r}; a reading needs an "
                f"integer {field}. The producer must print one JSON object with integer value "
                f"and total, and a findings list."
            )
    reading = {
        "at": _now(clock),
        "kpi": kpi_id,
        "value": payload["value"],
        "total": payload["total"],
        "source": str(payload.get("source") or ""),
        "findings": payload.get("findings") or [],
        "producer_output_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }
    goal["measurements"].append(reading)
    save(repo, data)
    return reading


def _run_producer(repo: Path, producer: str) -> tuple[dict[str, Any], str]:
    completed = subprocess.run(
        [sys.executable, str(repo / producer)],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            f"{producer} exited {completed.returncode}: "
            f"{(completed.stderr or completed.stdout).strip()[:400]}"
        )
    try:
        return json.loads(completed.stdout), completed.stdout
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{producer} did not print JSON ({exc}). It must print one object with integer "
            f"value and total, a source string, and a findings list."
        ) from None


# --------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------


def record_decision(
    repo: Path, *, decided: str, because: str, expected: str, clock: Any = None
) -> dict[str, Any]:
    """Record what was decided, why, and what it should do to the number.

    Kept on the goal it belongs to, so replacing the goal does not carry its decisions forward.
    """

    data = load(repo)
    goal = current_goal(data)
    if goal is None:
        raise SystemExit(
            f"no goal is in force for {repo}. A decision with no goal cannot say what it moves; "
            f"run `goal_tracker.py set` first."
        )
    decision = {
        "at": _now(clock),
        "decided": decided.strip(),
        "because": because.strip(),
        "expected": expected.strip(),
    }
    goal.setdefault("decisions", []).append(decision)
    save(repo, data)
    return decision


def readings(goal: dict[str, Any], kpi_id: str) -> list[dict[str, Any]]:
    return [row for row in goal.get("measurements", []) if row.get("kpi") == kpi_id]


def report_lines(repo: Path, *, now_clause: str = "") -> list[str]:
    """The three lines, every figure read from the store rather than composed."""

    data = load(repo)
    goal = current_goal(data)
    if goal is None:
        return [
            "GOAL    none declared — run goal_tracker.py set",
            "SINCE   not comparable — no goal is in force",
            "NOW     nothing measurable until a goal and its KPIs are declared",
        ]
    lines = []
    for index, kpi in enumerate(goal["kpis"]):
        taken = readings(goal, kpi["id"])
        if not taken:
            lines.append(f"GOAL    {kpi['question']} · not yet measured")
            if index == 0:
                lines.append("SINCE   not comparable — this KPI has never been read")
            continue
        latest = taken[-1]
        lines.append(f"GOAL    {kpi['question']} · {latest['value']} of {latest['total']}")
        if index == 0:
            lines.append(f"SINCE   {_since_clause(goal, kpi, taken)}")
    lines.append(f"NOW     {now_clause or 'nothing running · next number when a KPI is measured'}")
    decisions = goal.get("decisions") or []
    if decisions:
        latest = decisions[-1]
        lines.append(
            f"WHY     {latest['decided']} — because {latest['because']} — "
            f"expected: {latest['expected']}"
        )
    return lines


def _since_clause(goal: dict[str, Any], kpi: dict[str, Any], taken: list[dict[str, Any]]) -> str:
    latest = taken[-1]
    if len(taken) < 2:
        return f"not comparable — first reading of {kpi['id']} under goal {goal['id']}"
    previous = taken[-2]
    if previous["total"] != latest["total"]:
        return (
            f"not comparable — the set grew from {previous['total']} to {latest['total']}; "
            f"{previous['value']} then, {latest['value']} now"
        )
    delta = latest["value"] - previous["value"]
    moved = f"+{delta}" if delta > 0 else str(delta)
    if delta == 0:
        return f"0 since the last reading — {kpi['id']} unchanged"
    failing = {str(item.get("item") or "") for item in latest.get("findings") or []}
    was = {str(item.get("item") or "") for item in previous.get("findings") or []}
    fixed = sorted(was - failing)
    broke = sorted(failing - was)
    detail = ", ".join(
        part
        for part in (
            f"fixed: {', '.join(fixed)}" if fixed else "",
            f"newly failing: {', '.join(broke)}" if broke else "",
        )
        if part
    )
    return f"{moved} since the last reading — {detail or kpi['id'] + ' moved'}"


def check_goal_line(repo: Path, line: str) -> tuple[bool, str]:
    """What a gate calls: does this GOAL line match what the store would render?"""

    expected = [row for row in report_lines(repo) if row.startswith("GOAL")]
    if any(line.strip() == row.strip() for row in expected):
        return True, ""
    rendered = "\n".join(expected) or "(no goal declared)"
    return False, (
        "the GOAL line does not match the declared goal. The store renders:\n"
        f"{rendered}\n"
        "Run `goal_tracker.py report` and paste its lines, or `goal_tracker.py measure` "
        "if the number is stale."
    )


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("set", help="declare a new goal and its KPIs, by interview; takes no arguments")
    sub.add_parser("show", help="print the stored goal, its KPIs and its readings")
    report = sub.add_parser("report", help="print the three report lines")
    report.add_argument("--now", default="", help="what is running, for the NOW line")
    take = sub.add_parser("measure", help="run a KPI's producer and record what it returned")
    take.add_argument("--kpi", required=True)
    decide = sub.add_parser("decide", help="record what was decided, why, and its expected effect")
    decide.add_argument("--decided", required=True)
    decide.add_argument("--because", required=True)
    decide.add_argument("--expected", required=True)
    gate = sub.add_parser("check", help="does a GOAL line match the declared goal")
    gate.add_argument("--goal-line", required=True)
    args = parser.parse_args(argv)
    repo = args.repo.resolve()

    if args.command == "set":
        answers = script_intake.collect(GOAL_SPEC)
        goal = set_goal(repo, answers)
        print(f"goal {goal['id']} recorded: {goal['statement']}")
        for kpi in goal["kpis"]:
            print(f"  KPI {kpi['id']} — {kpi['question']} (producer {kpi['producer']})")
        return 0

    if args.command == "show":
        print(json.dumps(load(repo), indent=2))
        return 0

    if args.command == "report":
        for line in report_lines(repo, now_clause=args.now):
            print(line)
        return 0

    if args.command == "decide":
        decision = record_decision(
            repo, decided=args.decided, because=args.because, expected=args.expected
        )
        print(f"recorded: {decision['decided']}")
        return 0

    if args.command == "measure":
        reading = measure(repo, args.kpi)
        print(f"{reading['kpi']}: {reading['value']} of {reading['total']}")
        for item in reading["findings"]:
            print(f"  {item.get('item')}: {', '.join(item.get('failed') or [])}")
        return 0

    ok, why = check_goal_line(repo, args.goal_line)
    if ok:
        return 0
    print(why, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
