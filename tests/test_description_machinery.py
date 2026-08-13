from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "description-machinery"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


from_intent = _load("description_from_intent", SKILL / "from_intent.py")
collect_noticed = _load("description_collect_noticed", SKILL / "collect_noticed.py")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_reader_launcher_streams_safe_persistent_telemetry_and_preserves_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    readers = _load("description_readers_telemetry", SKILL / "readers.py")
    worker = tmp_path / "fake_reader.py"
    worker.write_text(
        """import json
import sys
import time
from pathlib import Path

payload = json.loads(sys.stdin.read())
print(json.dumps({"type": "item.started", "item": {"type": "command_execution", "command": "pytest focused.py"}}), flush=True)
while payload.get("release") and not Path(payload["release"]).exists():
    time.sleep(0.01)
if payload["fail"]:
    print(json.dumps({"type": "turn.failed", "error": {"message": "SECRET REPOSITORY TEXT"}}), flush=True)
    print("private stderr detail", file=sys.stderr)
    raise SystemExit(7)
out = Path(payload["out"])
scratch = Path(payload["scratch"])
out.mkdir(parents=True, exist_ok=True)
scratch.mkdir(parents=True, exist_ok=True)
(out / "answer.json").write_text("{}", encoding="utf-8")
(scratch / "reader.json").write_text(json.dumps({"model": "model-a", "harness": "codex"}), encoding="utf-8")
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(readers, "validate_reader_command", lambda _command: [sys.executable, str(worker)])
    work = tmp_path / "work"
    work.mkdir()

    def job(name: str, fail: bool, release: Path | None = None) -> dict[str, object]:
        out = work / name
        scratch = work / f"{name}-scratch"
        return {
            "stage": "look", "waiting_for": str(out), "scratch": str(scratch),
            "instruction": json.dumps({
                "out": str(out), "scratch": str(scratch), "fail": fail,
                "private": "SECRET REPOSITORY TEXT", "release": str(release) if release else "",
            }),
        }

    release = work / "release"
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(
            readers._launch, [job("success", False, release)], "reader", tmp_path, work, "read",
        )
        deadline = time.monotonic() + 2
        live = ""
        while time.monotonic() < deadline:
            live = (work / "feed.jsonl").read_text(encoding="utf-8") \
                if (work / "feed.jsonl").exists() else ""
            if '"doing": "command_execution pytest"' in live:
                break
            time.sleep(0.01)
        assert '"what": "agent started"' in live
        assert '"doing": "command_execution pytest"' in live
        assert '"what": "agent finished"' not in live
        assert not running.done()
        release.write_text("continue", encoding="utf-8")
        success = running.result()[0]
    failure_one = readers._launch([job("failure", True)], "reader", tmp_path, work, "read")[0]
    failure_two = readers._launch([job("failure", True)], "reader", tmp_path, work, "read")[0]

    logs = sorted(work.glob("launch-*.log"))
    feed_text = (work / "feed.jsonl").read_text(encoding="utf-8")
    feed = [json.loads(line) for line in feed_text.splitlines()]
    assert len(logs) == 3
    assert len({path.name for path in logs}) == 3
    assert success["delivery"] == "delivered"
    assert success["model"] == "model-a" and success["harness"] == "codex"
    assert failure_one["exit_code"] == failure_two["exit_code"] == 7
    assert failure_one["log"] != failure_two["log"]
    assert any(row["what"] == "agent started" and row["stage"] == "look" for row in feed)
    assert any(row.get("doing") == "command_execution pytest" for row in feed)
    assert any(row["what"] == "agent failure" and row["error"] == "turn.failed" for row in feed)
    assert any(
        row["what"] == "agent finished" and row["exit_code"] == 0
        and row["model"] == "model-a" and row["delivery"] == "delivered"
        for row in feed
    )
    assert "SECRET REPOSITORY TEXT" not in feed_text
    assert "SECRET REPOSITORY TEXT" in Path(str(failure_one["log"])).read_text(encoding="utf-8")


def _fill_look(work: Path, *, quote: str, quoted_from: Path) -> None:
    for pass_number in range(1, 3):
        for question in from_intent.QUESTIONS:
            _write_json(
                work / f"look-{pass_number}" / f"{question['id']}.json",
                {
                    "id": question["id"],
                    "answered": "yes",
                    "answer": "reader answer",
                    "quote": quote,
                    "quoted_from": str(quoted_from),
                },
            )


def _fill_no_answers(work: Path) -> None:
    for pass_number in range(1, 3):
        for question in from_intent.QUESTIONS:
            _write_json(
                work / f"look-{pass_number}" / f"{question['id']}.json",
                {
                    "id": question["id"],
                    "answered": "no",
                    "answer": "",
                    "quote": "nothing in the supplied sources answers this",
                    "quoted_from": "",
                },
            )


def test_from_intent_blocks_a_quote_absent_from_authorized_sources(tmp_path: Path) -> None:
    intent = tmp_path / "intent.md"
    context = tmp_path / "context.md"
    work = tmp_path / "work"
    intent.write_text("REAL INTENT", encoding="utf-8")
    context.write_text("REAL CONTEXT", encoding="utf-8")

    from_intent.drive(intent, work, [context])
    _fill_look(work, quote="FABRICATED QUOTE", quoted_from=context)
    result = from_intent.drive(intent, work, [context])

    assert result["status"] == "blocked"
    assert result["stopped"] == "invalid source quotation"
    assert result["invalid_records"]
    assert not list(work.glob("*description*"))


def test_from_intent_accepts_an_exact_quote_from_an_authorized_source(tmp_path: Path) -> None:
    intent = tmp_path / "intent.md"
    context = tmp_path / "context.md"
    work = tmp_path / "work"
    intent.write_text("REAL INTENT", encoding="utf-8")
    context.write_text("REAL CONTEXT", encoding="utf-8")

    from_intent.drive(intent, work, [context])
    _fill_look(work, quote="REAL CONTEXT", quoted_from=context)
    result = from_intent.drive(intent, work, [context])

    assert result["answered_by_what_was_given"] == len(from_intent.QUESTIONS)
    assert result["to_ask"] == []


def test_collector_blocks_a_quote_absent_from_the_builder_note(tmp_path: Path) -> None:
    build_work = tmp_path / "build-work"
    order = tmp_path / "order.json"
    out = tmp_path / "out"
    _write_json(build_work / "build-r1" / "change.json", {"left_alone": "REAL BUILDER NOTE"})
    _write_json(order, {"rounds": []})
    collect_noticed.collect(build_work, order, out)
    for pass_number in range(1, 3):
        _write_json(
            out / f"noticed-{pass_number}" / "thing.json",
            {
                "source_item": "r1",
                "quote": "FABRICATED BUILDER QUOTE",
                "in_your_words": "work",
            },
        )

    result = collect_noticed.collect(build_work, order, out)

    assert result["status"] == "blocked"
    assert result["stopped"] == "invalid source quotation"
    assert result["invalid_records"]
    assert not (out / "noticed-description.md").exists()


def test_collector_accepts_an_exact_quote_from_the_builder_note(tmp_path: Path) -> None:
    build_work = tmp_path / "build-work"
    order = tmp_path / "order.json"
    out = tmp_path / "out"
    _write_json(build_work / "build-r1" / "change.json", {"left_alone": "REAL BUILDER NOTE"})
    _write_json(order, {"rounds": []})
    collect_noticed.collect(build_work, order, out)
    for pass_number in range(1, 3):
        _write_json(
            out / f"noticed-{pass_number}" / "thing.json",
            {
                "source_item": "r1",
                "quote": "REAL BUILDER NOTE",
                "in_your_words": "work",
            },
        )

    result = collect_noticed.collect(build_work, order, out)

    assert result["stopped"] == "judging what was noticed"
    assert result["pairs"] == 1


def _approve_pair(directory: Path, pair_id: str, filename: str) -> None:
    _write_json(
        directory / filename,
        {
            "pair_id": pair_id,
            "same_thing": "yes",
            "is_work": "yes",
            "covered_by": None,
            "why": "accepted",
        },
    )


def test_collector_keeps_a_missing_expected_judgement_outstanding(tmp_path: Path) -> None:
    build_work = tmp_path / "build-work"
    order = tmp_path / "order.json"
    out = tmp_path / "out"
    _write_json(build_work / "build-r1" / "change.json", {"left_alone": "REAL BUILDER NOTE"})
    _write_json(order, {"rounds": []})
    collect_noticed.collect(build_work, order, out)
    for pass_number in range(1, 3):
        _write_json(
            out / f"noticed-{pass_number}" / "thing.json",
            {"source_item": "r1", "quote": "REAL BUILDER NOTE", "in_your_words": "work"},
        )
    collect_noticed.collect(build_work, order, out)
    expected = json.loads((out / "noticed-pairs.json").read_text(encoding="utf-8"))["pairs"][0]["pair_id"]
    for pass_number in range(1, 3):
        _approve_pair(out / f"judged-{pass_number}", "wrong-pair", "wrong.json")

    result = collect_noticed.collect(build_work, order, out)

    assert result["stopped"] == "judging what was noticed"
    assert result["outstanding"] == 2
    assert result["missing_pair_ids"] == {"1": [expected], "2": [expected]}
    assert not (out / "noticed-description.md").exists()


def test_collector_keeps_a_missing_cross_builder_judgement_outstanding(tmp_path: Path) -> None:
    build_work = tmp_path / "build-work"
    order = tmp_path / "order.json"
    out = tmp_path / "out"
    _write_json(build_work / "build-r1" / "change.json", {"left_alone": "SHARED REAL NOTE"})
    _write_json(build_work / "build-r2" / "change.json", {"left_alone": "SHARED REAL NOTE"})
    _write_json(order, {"rounds": []})
    collect_noticed.collect(build_work, order, out)
    for pass_number in range(1, 3):
        for item in ("r1", "r2"):
            _write_json(
                out / f"noticed-{pass_number}" / f"{item}.json",
                {"source_item": item, "quote": "SHARED REAL NOTE", "in_your_words": "work"},
            )
    collect_noticed.collect(build_work, order, out)
    expected_judged = [
        row["pair_id"]
        for row in json.loads((out / "noticed-pairs.json").read_text(encoding="utf-8"))["pairs"]
    ]
    for pass_number in range(1, 3):
        for index, pair_id in enumerate(expected_judged):
            _approve_pair(out / f"judged-{pass_number}", pair_id, f"{index}.json")
    deciding = collect_noticed.collect(build_work, order, out)
    assert deciding["stopped"] == "deciding which of these are one thing"
    expected_same = json.loads((out / "same-pairs.json").read_text(encoding="utf-8"))["pairs"][0]["pair_id"]
    for pass_number in range(1, 3):
        _write_json(
            out / f"same-{pass_number}" / "wrong.json",
            {"pair_id": "wrong-pair", "same_thing": "yes", "why": "wrong identity"},
        )

    result = collect_noticed.collect(build_work, order, out)

    assert result["stopped"] == "deciding which of these are one thing"
    assert result["outstanding"] == 2
    assert result["missing_pair_ids"] == {"1": [expected_same], "2": [expected_same]}
    assert not (out / "noticed-description.md").exists()


def test_from_intent_blocks_reuse_after_context_content_changes(tmp_path: Path) -> None:
    intent = tmp_path / "intent.md"
    context = tmp_path / "context.md"
    work = tmp_path / "work"
    intent.write_text("INTENT", encoding="utf-8")
    context.write_text("OLD QUOTE", encoding="utf-8")
    from_intent.drive(intent, work, [context])
    _fill_look(work, quote="OLD QUOTE", quoted_from=context)
    first = from_intent.drive(intent, work, [context])
    assert first["answered_by_what_was_given"] == len(from_intent.QUESTIONS)

    context.write_text("NEW QUOTE", encoding="utf-8")
    second = from_intent.drive(intent, work, [context])

    assert second["status"] == "blocked"
    assert second["stopped"] == "input changed"
    assert second["use_fresh_work_directory"] is True


def test_collector_blocks_reuse_after_builder_notes_change(tmp_path: Path) -> None:
    build_work = tmp_path / "build-work"
    order = tmp_path / "order.json"
    out = tmp_path / "out"
    change = build_work / "build-r1" / "change.json"
    _write_json(change, {"left_alone": "OLD NOTE"})
    _write_json(order, {"rounds": []})
    first = collect_noticed.collect(build_work, order, out)
    assert first["stopped"] == "reading what the builders noticed"

    _write_json(change, {"left_alone": "NEW NOTE"})
    second = collect_noticed.collect(build_work, order, out)

    assert second["status"] == "blocked"
    assert second["stopped"] == "input changed"
    assert second["use_fresh_output_directory"] is True


def test_from_intent_emits_a_description_from_agreed_sourced_answers(tmp_path: Path) -> None:
    intent = tmp_path / "intent.md"
    context = tmp_path / "context.md"
    work = tmp_path / "work"
    intent.write_text("INTENT", encoding="utf-8")
    context.write_text("ONE EXACT ANSWER", encoding="utf-8")
    from_intent.drive(intent, work, [context])
    _fill_look(work, quote="ONE EXACT ANSWER", quoted_from=context)

    result = from_intent.drive(intent, work, [context])

    assert result["status"] == "complete"
    description = Path(result["description"]).read_text(encoding="utf-8")
    assert description.count("ONE EXACT ANSWER") == len(from_intent.QUESTIONS)
    assert description.count(str(context.resolve())) == len(from_intent.QUESTIONS)
    for question in from_intent.QUESTIONS:
        assert question["asks"] in description


def test_from_intent_emits_owner_handback_when_sources_do_not_answer(tmp_path: Path) -> None:
    intent = tmp_path / "intent.md"
    work = tmp_path / "work"
    intent.write_text("INTENT", encoding="utf-8")
    from_intent.drive(intent, work, [])
    _fill_no_answers(work)

    result = from_intent.drive(intent, work, [])

    assert result["status"] == "needs_owner"
    assert "description" not in result
    sheet = Path(result["sheet"]).read_text(encoding="utf-8")
    assert "--owner-answers" in sheet
    assert "fresh" in sheet.lower()


def test_from_intent_accepts_owner_answers_as_an_authorized_source(tmp_path: Path) -> None:
    intent = tmp_path / "intent.md"
    owner_answers = tmp_path / "owner-answers.md"
    work = tmp_path / "work"
    intent.write_text("INTENT", encoding="utf-8")
    owner_answers.write_text("OWNER EXACT ANSWER", encoding="utf-8")
    from_intent.drive(intent, work, [], owner_answers=owner_answers)
    _fill_look(work, quote="OWNER EXACT ANSWER", quoted_from=owner_answers)

    result = from_intent.drive(intent, work, [], owner_answers=owner_answers)

    assert result["status"] == "complete"
    description = Path(result["description"]).read_text(encoding="utf-8")
    assert "OWNER EXACT ANSWER" in description
    assert str(owner_answers.resolve()) in description


def test_from_intent_hands_differing_valid_citations_to_the_owner(tmp_path: Path) -> None:
    intent = tmp_path / "intent.md"
    context = tmp_path / "context.md"
    work = tmp_path / "work"
    intent.write_text("INTENT", encoding="utf-8")
    context.write_text("FIRST EXACT ANSWER\nSECOND EXACT ANSWER", encoding="utf-8")
    from_intent.drive(intent, work, [context])
    for pass_number, quote in ((1, "FIRST EXACT ANSWER"), (2, "SECOND EXACT ANSWER")):
        for question in from_intent.QUESTIONS:
            _write_json(
                work / f"look-{pass_number}" / f"{question['id']}.json",
                {
                    "id": question["id"],
                    "answered": "yes",
                    "answer": "reader answer",
                    "quote": quote,
                    "quoted_from": str(context),
                },
            )

    result = from_intent.drive(intent, work, [context])

    assert result["status"] == "needs_owner"
    assert result["to_ask"][0]["why"] == "the readers cited different answers"
    sheet = Path(result["sheet"]).read_text(encoding="utf-8")
    assert "FIRST EXACT ANSWER" in sheet
    assert "SECOND EXACT ANSWER" in sheet
    assert "description" not in result


def test_from_intent_keeps_wrong_question_identities_outstanding(tmp_path: Path) -> None:
    intent = tmp_path / "intent.md"
    context = tmp_path / "context.md"
    work = tmp_path / "work"
    intent.write_text("INTENT", encoding="utf-8")
    context.write_text("EXACT ANSWER", encoding="utf-8")
    from_intent.drive(intent, work, [context])
    for pass_number in range(1, 3):
        for index in range(len(from_intent.QUESTIONS)):
            _write_json(
                work / f"look-{pass_number}" / f"wrong-{index}.json",
                {
                    "id": f"wrong-{index}",
                    "answered": "yes",
                    "answer": "reader answer",
                    "quote": "EXACT ANSWER",
                    "quoted_from": str(context),
                },
            )

    result = from_intent.drive(intent, work, [context])

    expected = [question["id"] for question in from_intent.QUESTIONS]
    assert result["status"] == "waiting_for_readers"
    assert result["missing_question_ids"] == {"1": expected, "2": expected}


def test_from_intent_cli_distinguishes_waiting_owner_and_complete(tmp_path: Path) -> None:
    intent = tmp_path / "intent.md"
    context = tmp_path / "context.md"
    work = tmp_path / "work"
    intent.write_text("INTENT", encoding="utf-8")
    context.write_text("EXACT ANSWER", encoding="utf-8")
    args = ["--intent", str(intent), "--context", str(context), "--work", str(work)]

    assert from_intent.main(args) == 2
    _fill_no_answers(work)
    assert from_intent.main(args) == 4

    complete_work = tmp_path / "complete-work"
    complete_args = [
        "--intent", str(intent), "--context", str(context), "--work", str(complete_work),
    ]
    from_intent.drive(intent, complete_work, [context])
    _fill_look(complete_work, quote="EXACT ANSWER", quoted_from=context)
    assert from_intent.main(complete_args) == 0


def test_collector_cli_distinguishes_empty_waiting_and_blocked(tmp_path: Path) -> None:
    empty_work = tmp_path / "empty-build-work"
    order = tmp_path / "order.json"
    _write_json(order, {"rounds": []})
    assert collect_noticed.main([
        "--work", str(empty_work), "--order", str(order), "--out", str(tmp_path / "empty-out"),
    ]) == 0

    build_work = tmp_path / "build-work"
    out = tmp_path / "out"
    _write_json(build_work / "build-r1" / "change.json", {"left_alone": "REAL NOTE"})
    args = ["--work", str(build_work), "--order", str(order), "--out", str(out)]
    assert collect_noticed.main(args) == 2
    for pass_number in range(1, 3):
        _write_json(
            out / f"noticed-{pass_number}" / "thing.json",
            {"source_item": "r1", "quote": "INVENTED", "in_your_words": "work"},
        )
    assert collect_noticed.main(args) == 3


def test_collector_completes_one_valid_note_through_its_real_function_path(tmp_path: Path) -> None:
    build_work = tmp_path / "build-work"
    order = tmp_path / "order.json"
    out = tmp_path / "out"
    _write_json(build_work / "build-r1" / "change.json", {"left_alone": "REAL NOTE"})
    _write_json(order, {"rounds": []})
    collect_noticed.collect(build_work, order, out)
    for pass_number in range(1, 3):
        _write_json(
            out / f"noticed-{pass_number}" / "thing.json",
            {"source_item": "r1", "quote": "REAL NOTE", "in_your_words": "work"},
        )
    collect_noticed.collect(build_work, order, out)
    pair_id = json.loads((out / "noticed-pairs.json").read_text(encoding="utf-8"))["pairs"][0]["pair_id"]
    for pass_number in range(1, 3):
        _approve_pair(out / f"judged-{pass_number}", pair_id, "answer.json")

    result = collect_noticed.collect(build_work, order, out)

    assert result["status"] == "complete"
    description = Path(result["description"]).read_text(encoding="utf-8")
    assert "REAL NOTE" in description


def test_from_intent_completes_through_the_documented_cli(tmp_path: Path) -> None:
    intent = tmp_path / "intent.md"
    context = tmp_path / "context.md"
    work = tmp_path / "work"
    intent.write_text("INTENT", encoding="utf-8")
    context.write_text("CLI EXACT ANSWER", encoding="utf-8")
    command = [
        sys.executable,
        str(SKILL / "from_intent.py"),
        "--intent", str(intent),
        "--context", str(context),
        "--work", str(work),
    ]

    waiting = subprocess.run(command, capture_output=True, text=True)
    assert waiting.returncode == 2
    assert json.loads(waiting.stdout)["status"] == "waiting_for_readers"
    _fill_look(work, quote="CLI EXACT ANSWER", quoted_from=context)
    complete = subprocess.run(command, capture_output=True, text=True)

    assert complete.returncode == 0
    result = json.loads(complete.stdout)
    assert result["status"] == "complete"
    assert Path(result["description"]).is_file()


def test_collector_completes_through_the_documented_cli(tmp_path: Path) -> None:
    build_work = tmp_path / "build-work"
    order = tmp_path / "order.json"
    out = tmp_path / "out"
    _write_json(build_work / "build-r1" / "change.json", {"left_alone": "CLI REAL NOTE"})
    _write_json(order, {"rounds": []})
    command = [
        sys.executable,
        str(SKILL / "collect_noticed.py"),
        "--work", str(build_work),
        "--order", str(order),
        "--out", str(out),
    ]

    notice = subprocess.run(command, capture_output=True, text=True)
    assert notice.returncode == 2
    for pass_number in range(1, 3):
        _write_json(
            out / f"noticed-{pass_number}" / "thing.json",
            {"source_item": "r1", "quote": "CLI REAL NOTE", "in_your_words": "work"},
        )
    judge = subprocess.run(command, capture_output=True, text=True)
    assert judge.returncode == 2
    pair_id = json.loads((out / "noticed-pairs.json").read_text(encoding="utf-8"))["pairs"][0]["pair_id"]
    for pass_number in range(1, 3):
        _approve_pair(out / f"judged-{pass_number}", pair_id, "answer.json")
    complete = subprocess.run(command, capture_output=True, text=True)

    assert complete.returncode == 0
    result = json.loads(complete.stdout)
    assert result["status"] == "complete"
    assert "CLI REAL NOTE" in Path(result["description"]).read_text(encoding="utf-8")
