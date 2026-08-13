"""Contract regressions for the end-to-end Requirements Machinery controller."""
from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
MACHINE = ROOT / "skills" / "requirements-machine"
sys.dont_write_bytecode = True


def load_module(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_owner_decision_recording_refuses_unoffered_choices(tmp_path: Path) -> None:
    decisions = load_module("requirements_owner_decisions", MACHINE / "owner_decisions.py")
    path = tmp_path / "owner-decisions.json"
    available = {"merge:a|b": {"keep both", "merge"}}

    with pytest.raises(ValueError, match="must be one of"):
        decisions.record(path, available, "merge:a|b", "delete both")
    decisions.record(path, available, "merge:a|b", "keep both")

    assert decisions.load(path) == {"merge:a|b": "keep both"}


def test_owner_keep_both_resolves_merge_disagreement_without_editing_reader_records(
    tmp_path: Path,
) -> None:
    consolidate = load_module("requirements_consolidate_owner", MACHINE / "consolidate.py")
    records = tmp_path / "records"
    merge_1, merge_2 = tmp_path / "merge-1", tmp_path / "merge-2"
    write_json(records / "a.json", {"id": "a", "requirement": "First", "check": "one"})
    write_json(records / "b.json", {"id": "b", "requirement": "Second", "check": "two"})
    write_json(merge_1 / "pair.json", {
        "left": "a", "right": "b", "verdict": "merge", "why": "same",
    })
    write_json(merge_2 / "pair.json", {
        "left": "a", "right": "b", "verdict": "keep both", "why": "different",
    })
    owner = tmp_path / "owner-decisions.json"
    write_json(owner, {"schema_version": 1, "decisions": [{
        "decision_id": "merge:a|b", "choice": "keep both", "decided_by": "owner",
    }]})

    result = consolidate.consolidate([records], [merge_1, merge_2], owner)

    assert result["count"] == 2
    assert result["merges_refused_for_disagreement"] == []
    assert result["merges_resolved_by_owner"] == [
        {"left": "a", "right": "b", "choice": "keep both"},
    ]


def test_reader_launcher_streams_safe_persistent_telemetry_and_preserves_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    readers = load_module("requirements_readers_telemetry", MACHINE / "readers.py")
    worker = tmp_path / "fake_reader.py"
    worker.write_text(
        """import json
import sys
import time
from pathlib import Path

payload = json.loads(sys.stdin.read())
print(json.dumps({"type": "item.started", "item": {"id": "tool-1", "type": "command_execution", "command": "pytest focused.py"}}), flush=True)
print(json.dumps({"type": "item.completed", "item": {"id": "tool-1", "type": "command_execution", "command": "pytest focused.py"}}), flush=True)
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
(scratch / "reader.json").write_text(json.dumps({"model": "model-b", "harness": "claude"}), encoding="utf-8")
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
            "stage": "oblige", "waiting_for": str(out), "scratch": str(scratch),
            "expected_count": 1,
            "instruction": json.dumps({
                "out": str(out), "scratch": str(scratch), "fail": fail,
                "private": "SECRET REPOSITORY TEXT", "release": str(release) if release else "",
            }),
        }

    release = work / "release"
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(
            readers.launch, [job("success", False, release)], "reader", tmp_path, work, "read",
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
    failure_one = readers.launch([job("failure", True)], "reader", tmp_path, work, "read")[0]
    failure_two = readers.launch([job("failure", True)], "reader", tmp_path, work, "read")[0]

    logs = sorted(work.glob("launch-*.log"))
    feed_text = (work / "feed.jsonl").read_text(encoding="utf-8")
    feed = [json.loads(line) for line in feed_text.splitlines()]
    assert len(logs) == 3
    assert len({path.name for path in logs}) == 3
    assert success["delivery"] == "delivered"
    assert success["model"] == "model-b" and success["harness"] == "claude"
    assert failure_one["exit_code"] == failure_two["exit_code"] == 7
    assert failure_one["log"] != failure_two["log"]
    assert any(row["what"] == "agent started" and row["stage"] == "oblige" for row in feed)
    assert any(row.get("doing") == "command_execution pytest" for row in feed)
    assert sum(row.get("doing") == "command_execution pytest" for row in feed) == 3
    assert any(row["what"] == "progress" and row["current"] == "answer"
               and row["completed"] == row["total"] == 1 for row in feed)
    assert any(row["what"] == "agent failure" and row["error"] == "turn.failed" for row in feed)
    assert any(
        row["what"] == "agent finished" and row["exit_code"] == 0
        and row["model"] == "model-b" and row["delivery"] == "delivered"
        for row in feed
    )
    assert "SECRET REPOSITORY TEXT" not in feed_text
    assert "SECRET REPOSITORY TEXT" in Path(str(failure_one["log"])).read_text(encoding="utf-8")


def test_reader_progress_reports_existing_records_once_as_a_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    readers = load_module("requirements_readers_progress_snapshot", MACHINE / "readers.py")
    worker = tmp_path / "fake_reader.py"
    worker.write_text("import sys\nsys.stdin.read()\n", encoding="utf-8")
    monkeypatch.setattr(readers, "validate_reader_command", lambda _command: [sys.executable, str(worker)])
    work = tmp_path / "work"
    out = work / "answers"
    out.mkdir(parents=True)
    write_json(out / "p1.json", {})
    write_json(out / "p2.json", {})

    readers.launch([{
        "stage": "answer", "waiting_for": str(out), "scratch": str(work / "scratch"),
        "expected_count": 3, "instruction": "finish",
    }], "reader", tmp_path, work, "read")

    feed = [json.loads(line) for line in (work / "feed.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row for row in feed if row["what"] == "progress"] == []
    snapshots = [row for row in feed if row["what"] == "progress snapshot"]
    assert len(snapshots) == 1
    assert snapshots[0]["completed"] == 2 and snapshots[0]["total"] == 3


def test_answer_and_settlement_require_semantic_support_explanations() -> None:
    machine = load_module("requirements_run_semantic_support", MACHINE / "run.py")
    citation = {"where": "impl.py", "line": 1, "text": "enabled = True"}

    assert machine._answer_record({
        "answer": "yes", "citations": [citation], "looked_at": "",
    }) == ["an answer must explain how the cited behavior resolves the exact part"]
    assert machine._answer_record({
        "answer": "yes", "citations": [citation],
        "looked_at": "The enabled assignment makes the requested behavior active.",
    }) == []
    assert machine._settle_record({
        "answer": "yes", "citations": [citation], "why_the_other_side_is_wrong": "",
    }) == ["a settlement must explain what the other side missed or misread"]


def test_obligation_coverage_returns_a_recoverable_incomplete_result(tmp_path: Path):
    coverage = load_module("requirements_coverage", MACHINE / "check_coverage.py")
    candidates = tmp_path / "obligations.json"
    write_json(candidates, {"obligations": [{"id": "o10"}, {"id": "o2"}, {"id": "o1"}]})
    records = tmp_path / "records"
    records.mkdir()

    result = coverage.check(candidates, records)

    assert result["complete"] is False
    assert result["unaccounted"] == ["o1", "o2", "o10"]


def test_stage_gate_rejects_count_complete_records_with_wrong_id_and_verdict(tmp_path: Path):
    gate = load_module("requirements_stage_gate", MACHINE / "stage_gate.py")
    records = tmp_path / "verify-1"
    write_json(records / "f1.json", {
        "candidate_id": "not-f1",
        "verdict": "probably",
        "citations": [{"where": "missing.py", "line": 1, "text": "missing"}],
    })

    result = gate.inspect(
        records,
        {"f1"},
        gate.field_identity("candidate_id"),
        gate.enum("verdict", {"holds", "wrong"}, require_citations=True),
    )

    assert result["complete"] is False
    assert result["missing"] == ["f1"]
    assert result["unknown"] == [{"file": "f1.json", "id": "not-f1"}]
    assert result["invalid"][0]["why"] == ["verdict must be one of ['holds', 'wrong']"]


def test_stage_gate_requires_record_identity_and_resolvable_citation_shape(tmp_path: Path):
    gate = load_module("requirements_stage_gate_strict", MACHINE / "stage_gate.py")
    records = tmp_path / "verify-1"
    write_json(records / "f1.json", {
        "verdict": "holds",
        "citations": ["a citation-shaped string is not executable evidence"],
    })

    result = gate.inspect(
        records, {"f1"}, gate.field_identity("candidate_id"),
        gate.enum("verdict", {"holds", "wrong"}, require_citations=True),
    )

    assert result["complete"] is False
    assert result["missing"] == ["f1"]
    assert result["unknown"] == [{"file": "f1.json", "id": ""}]
    assert result["invalid"][0]["why"] == ["citation 1 must be an object"]


def test_extra_unknown_reader_records_are_quarantined_without_becoming_retry_work(
    tmp_path: Path,
) -> None:
    machine = load_module("requirements_run_unknown_extras", MACHINE / "run.py")
    description = tmp_path / "description.md"
    description.write_text("Captured requirements description.\n", encoding="utf-8")
    work = tmp_path / "work"
    valid_ids = [f"L{index}" for index in range(1, 35)]
    extra_ids = ["L35", "L36", "L37", "L38"]
    write_json(work / "split.json", {
        "partition": {"balances": True},
        "obligations": [],
        "leftover": [
            {"id": candidate_id, "text": f"Captured leftover {candidate_id}."}
            for candidate_id in valid_ids
        ],
    })
    for pass_number in (1, 2):
        for candidate_id in valid_ids + extra_ids:
            write_json(work / f"leftover-{pass_number}" / f"{candidate_id}.json", {
                "candidate_id": candidate_id,
                "not_a_requirement_because": "The captured sentence states no obligation.",
                "evidence": f"Captured leftover {candidate_id}.",
            })

    result = machine.drive("captured subject", description, work, None)

    assert result["status"] == "complete"
    assert result["requirements"] == 0
    for pass_number in (1, 2):
        assert {path.stem for path in (work / f"leftover-{pass_number}").glob("*.json")} \
            == set(valid_ids)
        refused = work / f"leftover-{pass_number}-refused"
        assert {path.name.split("-")[0] for path in refused.glob("L*.json")} == set(extra_ids)


def test_wrong_fact_and_settlement_records_carry_actionable_evidence():
    machine = load_module("requirements_run_record_contracts", MACHINE / "run.py")

    assert machine._verify_record({
        "verdict": "wrong",
        "citations": [{"where": "impl.py", "line": 1, "text": "actual"}],
    }) == ["a wrong verdict must say what the description should say instead"]
    assert machine._settle_record({
        "answer": "no", "needed": "remove", "citations": ["not executable"],
    }) == [
        "citation 1 must be an object",
        "a settlement must explain what the other side missed or misread",
    ]


def test_final_evidence_comes_from_the_accepted_settlement_not_the_losing_reader(
    tmp_path: Path,
) -> None:
    machine = load_module("requirements_run_settlement_evidence", MACHINE / "run.py")
    write_json(tmp_path / "answer-1" / "r1.p1.json", {
        "part_id": "r1.p1", "answer": "no", "needed": "change",
        "citations": [{"where": "losing.py", "line": 1, "text": "the opposite"}],
    })
    write_json(tmp_path / "answer-2" / "r1.p1.json", {
        "part_id": "r1.p1", "answer": "yes", "needed": None,
        "citations": [{"where": "reader.py", "line": 2, "text": "partial support"}],
    })
    write_json(tmp_path / "settle-1" / "r1.p1.json", {
        "part_id": "r1.p1", "answer": "yes", "needed": None,
        "citations": [{"where": "accepted.py", "line": 3, "text": "accepted support"}],
    })

    evidence = machine._first_citation(
        tmp_path, "r1.p1", stages=("settle",), require_answer="yes",
    )

    assert evidence == {"where": "accepted.py", "line": 3, "text": "accepted support"}


def test_requirements_document_lists_every_unresolved_part() -> None:
    writer = load_module("requirements_writer_unresolved", MACHINE / "write_document.py")
    report = {
        "subject": "subject", "requirements": 1, "add": [], "change": [], "remove": [],
        "already_met": [], "for_a_person": [{
            "kind": "unresolved parts", "requirement": "r1",
            "calls": {"pass-1": "change", "pass-2": "change"},
            "because_these_parts_were_answered_differently": [
                {"part_id": "r1.p1", "part": "first unresolved part",
                 "calls": {"pass-1": "yes", "pass-2": "no"},
                 "needed_by_pass": {"pass-2": "change"}},
                {"part_id": "r1.p2", "part": "second unresolved part",
                 "calls": {"pass-1": "no", "pass-2": "no"},
                 "needed_by_pass": {"pass-1": "add", "pass-2": "change"}},
            ],
        }],
    }
    document = writer.compose(report, [{
        "id": "r1", "requirement": "Requirement one", "check": "Check it.", "from": [],
    }])

    assert "1 decision groups containing 2 unresolved parts" in document
    assert "`r1.p1` — first unresolved part" in document
    assert "`r1.p2` — second unresolved part" in document


def test_description_sources_survive_partition_and_requirement_document(tmp_path: Path) -> None:
    enumerator = load_module("requirements_sources", MACHINE / "enumerate_obligations.py")
    writer = load_module("requirements_sources_writer", MACHINE / "write_document.py")
    description = tmp_path / "description.md"
    description.write_text(
        "## One\nThe package must contain the six audits.\n\n"
        "_Source: `/tmp/pdf-pages.txt`_\n\n"
        "The operator approves the hypothesis.\n\n"
        "_Source: `/tmp/owner-answers.md`_\n",
        encoding="utf-8",
    )

    split = enumerator.enumerate_obligations(description, 6)
    obligation = next(row for row in split["obligations"] if "six audits" in row["text"])
    owner = next(row for row in split["leftover"] if "approves" in row["text"])
    assert obligation["sources"] == ["/tmp/pdf-pages.txt"]
    assert owner["sources"] == ["/tmp/owner-answers.md"]

    document = writer.compose({
        "subject": "subject", "requirements": 1, "add": ["r1"], "change": [],
        "remove": [], "already_met": [], "for_a_person": [],
    }, [{
        "id": "r1", "requirement": "The package contains audits.", "check": "Inspect it.",
        "from": ["oblige-1:o1"], "sources": ["/tmp/pdf-pages.txt"],
    }])
    assert "**Source of truth.** `/tmp/pdf-pages.txt`" in document


def test_citation_gate_rejects_external_and_demo_only_positive_evidence(tmp_path: Path) -> None:
    citations = load_module("requirements_citation_eligibility", MACHINE / "check_citations.py")
    built = tmp_path / "built"
    (built / "Tasks" / "demo").mkdir(parents=True)
    (built / "Tasks" / "demo" / "output.md").write_text("six audits\n", encoding="utf-8")
    records = tmp_path / "records"
    write_json(records / "r1.p1.json", {
        "part_id": "r1.p1", "answer": "yes",
        "citations": [{"where": "Tasks/demo/output.md", "line": 1, "text": "six audits"}],
    })

    result = citations.check(records, built)

    assert result["refused"] == 1
    assert "production code or an executable contract" in result["refusals"][0]["unresolved"][0]
    external = citations._resolve(built, {
        "where": str(tmp_path / "outside.py"), "line": 1, "text": "anything",
    })
    assert external == {"ok": False, "why": f"{tmp_path / 'outside.py'} is outside the measured repository"}


def test_neutral_evidence_map_is_shared_and_tags_source_kind(tmp_path: Path) -> None:
    evidence = load_module("requirements_evidence_map", MACHINE / "evidence_map.py")
    built = tmp_path / "built"
    (built / "src").mkdir(parents=True)
    (built / "src" / "brief.py").write_text(
        "def build_question_bank():\n    return 'tailored question bank'\n", encoding="utf-8",
    )
    (built / "Tasks" / "demo").mkdir(parents=True)
    (built / "Tasks" / "demo" / "brief.md").write_text("tailored question bank\n", encoding="utf-8")
    parts = tmp_path / "parts.json"
    write_json(parts, {"parts": [{"part_id": "r1.p1", "part": "A tailored question bank exists."}]})

    result = evidence.build(parts, built)

    row = result["map"][0]
    assert result["neutrality"].startswith("Candidates only")
    assert {candidate["source_kind"] for candidate in row["candidates"]} == {"production"}
    assert evidence.source_kind(Path("Tasks/demo/brief.md")) == "example_or_output"
    assert any(candidate["symbol"] == "build_question_bank" for candidate in row["candidates"])


def test_add_vs_change_is_derived_from_evidence_not_reader_label() -> None:
    machine = load_module("requirements_needed_from_evidence", MACHINE / "run.py")
    disputes = load_module("requirements_dispute_needed", MACHINE / "gather_disputes.py")
    cited = {"answer": "no", "needed": "add", "citations": [{"where": "impl.py"}]}
    uncited = {"answer": "no", "needed": "change", "citations": []}
    removal = {"answer": "no", "needed": "remove", "citations": [{"where": "impl.py"}]}

    assert machine._needed_from_evidence(cited) == disputes.needed_from_evidence(cited) == "change"
    assert machine._needed_from_evidence(uncited) == disputes.needed_from_evidence(uncited) == "add"
    assert machine._needed_from_evidence(removal) == "remove"


def test_one_bounded_resplit_replaces_only_the_disputed_coarse_part(tmp_path: Path) -> None:
    machine = load_module("requirements_resplit", MACHINE / "run.py")
    parts = {
        "parts": [
            {"part_id": "r1.p1", "requirement_id": "r1", "requirement": "R1",
             "part": "The engine checks and blocks."},
            {"part_id": "r2.p1", "requirement_id": "r2", "requirement": "R2",
             "part": "The report exists."},
        ],
        "count": 2,
    }
    write_json(tmp_path / "resplit-candidates.json", {
        "parts": [{"part_id": "r1.p1", "part": "The engine checks and blocks."}], "count": 1,
    })
    write_json(tmp_path / "resplit-1" / "r1.p1.json", {
        "part_id": "r1.p1", "verdict": "split",
        "parts": [{"part": "The engine checks."}, {"part": "The engine blocks."}],
        "why": "The original contains two independently verifiable actions.",
    })

    expanded = machine._apply_resplits(parts, tmp_path)

    assert [row["part_id"] for row in expanded["parts"]] == ["r1.p1.s1", "r1.p1.s2", "r2.p1"]
    assert expanded["count"] == 3
    assert machine._resplit_record({
        "part_id": "r1.p1", "verdict": "split", "parts": [{"part": "only one"}], "why": "x",
    }) == ["a split must return at least two parts"]


def test_client_policy_isolates_embedded_readers_without_switching_client(tmp_path: Path) -> None:
    policy = load_module("requirements_client_isolation", MACHINE / "client_model_policy.py")
    codex = tmp_path / "codex.json"
    write_json(codex, {
        "schema_version": 1, "client": "codex", "required_runtime": "codex exec",
        "forbidden_runtime": "claude", "fail_closed": True,
    })
    claude = tmp_path / "claude.json"
    write_json(claude, {
        "schema_version": 1, "client": "claude", "required_runtime": "claude -p",
        "forbidden_runtime": "codex exec", "fail_closed": True,
    })

    codex_command = policy.validate_reader_command("codex exec --json", codex)
    claude_command = policy.validate_reader_command("claude -p --output-format stream-json", claude)
    assert codex_command[:2] == ["codex", "exec"]
    assert {"--ignore-user-config", "--ephemeral"} <= set(codex_command)
    assert claude_command[:2] == ["claude", "-p"]
    assert {"--disable-slash-commands", "--strict-mcp-config", "--no-session-persistence"} \
        <= set(claude_command)
    with pytest.raises(ValueError, match="unrestricted host access"):
        policy.validate_reader_command(
            "codex exec --dangerously-bypass-approvals-and-sandbox", codex,
        )


def test_reader_launcher_enforces_policy_before_starting_any_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    readers = load_module("requirements_readers_policy_order", MACHINE / "readers.py")
    launched = []

    def refuse(_command: str):
        raise ValueError("wrong installed client")

    monkeypatch.setattr(readers, "validate_reader_command", refuse)
    monkeypatch.setattr(readers.subprocess, "Popen", lambda *args, **kwargs: launched.append(args))

    with pytest.raises(ValueError, match="wrong installed client"):
        readers.launch([
            {"instruction": "read", "waiting_for": str(tmp_path / "answers")},
        ], "forbidden reader", tmp_path, tmp_path, "test")

    assert launched == []


def test_greenfield_drive_preserves_both_passes_and_writes_both_documents(tmp_path: Path):
    machine = load_module("requirements_run_greenfield", MACHINE / "run.py")
    description = tmp_path / "description.md"
    description.write_text(
        "The product must emit a report for its owner. The report is available in Markdown.\n",
        encoding="utf-8",
    )
    work = tmp_path / "work"

    first = machine.drive("report product", description, work, None)
    assert first["status"] == "waiting_for_readers"
    obligation = json.loads((work / "obligations.json").read_text())["obligations"][0]
    leftover = json.loads((work / "leftover.json").read_text())["leftover"][0]
    required = {
        "candidate_id": obligation["id"],
        "requirement": "The product emits a report.",
        "source": obligation["text"],
        "check": "A report is emitted.",
    }
    for index in (1, 2):
        write_json(work / f"oblige-{index}" / f"{obligation['id']}.json", required)
    write_json(work / "leftover-1" / f"{leftover['id']}.json", {
        "candidate_id": leftover["id"],
        "not_a_requirement_because": "It repeats the report format without another obligation.",
        "evidence": leftover["text"],
    })
    write_json(work / "leftover-2" / f"{leftover['id']}.json", {
        "candidate_id": leftover["id"],
        "requirement": "The report is available in Markdown.",
        "source": leftover["text"],
        "check": "The emitted report is Markdown.",
    })

    merging = machine.drive("report product", description, work, None)
    assert merging["status"] == "waiting_for_readers"
    pairs = json.loads((work / "pairs.json").read_text())["pairs"]
    for index in (1, 2):
        for number, pair in enumerate(pairs, start=1):
            both_obligation = pair["left"].startswith("oblige-") and pair["right"].startswith("oblige-")
            write_json(work / f"merge-{index}" / f"p{number}.json", {
                "left": pair["left"],
                "right": pair["right"],
                "verdict": "merge" if both_obligation else "keep both",
                "surviving_requirement": "The product emits a report." if both_obligation else "",
                "why": "same obligation" if both_obligation else "distinct output constraint",
            })

    splitting = machine.drive("report product", description, work, None)
    assert splitting["status"] == "waiting_for_readers"
    requirements = json.loads((work / "requirements.json").read_text())["requirements"]
    assert len(requirements) == 2
    assert any(row["requirement"] == "The report is available in Markdown." for row in requirements)
    for row in requirements:
        write_json(work / "split-1" / f"{row['id']}.json", {
            "id": row["id"],
            "parts": [{"part_id": f"{row['id']}.p1", "part": row["requirement"]}],
        })

    complete = machine.drive("report product", description, work, None)
    assert complete["status"] == "complete"
    assert complete["add"] == ["r1", "r2"]
    assert Path(complete["document"]).is_file()
    assert Path(complete["breakdown"]).is_file()
    document = Path(complete["document"]).read_text()
    assert "Nothing is built yet" in document
    assert "measured against the build" not in document
    cli = subprocess.run([
        sys.executable, str(MACHINE / "run.py"),
        "--subject", "report product", "--description", str(description), "--work", str(work),
    ], capture_output=True, text=True, check=False)
    assert cli.returncode == 0
    assert json.loads(cli.stdout)["status"] == "complete"


def test_verification_gate_checks_real_citations_before_reading_requirements(tmp_path: Path):
    machine = load_module("requirements_run_verify", MACHINE / "run.py")
    description = tmp_path / "description.md"
    description.write_text("The product must emit a report [in code].\n", encoding="utf-8")
    built = tmp_path / "built"
    built.mkdir()
    (built / "impl.py").write_text("def emit():\n    return 'report'\n", encoding="utf-8")
    work = tmp_path / "work"

    waiting = machine.drive("report product", description, work, built)
    assert waiting["status"] == "waiting_for_readers"
    for index in (1, 2):
        write_json(work / f"verify-{index}" / "f1.json", {
            "candidate_id": "f1",
            "verdict": "holds",
            "citations": [{"where": "missing.py", "line": 1, "text": "not there"}],
        })

    refused = machine.drive("report product", description, work, built)
    assert refused["status"] == "waiting_for_readers"
    assert refused["stopped"] == "verifying the description"
    assert not (work / "oblige-1").exists()
    assert (work / "verify-1-refused" / "f1-1.json").is_file()
    cli = subprocess.run([
        sys.executable, str(MACHINE / "run.py"), "--subject", "report product",
        "--description", str(description), "--work", str(work), "--built", str(built),
    ], capture_output=True, text=True, check=False)
    assert cli.returncode == 2
    assert json.loads(cli.stdout)["status"] == "waiting_for_readers"


def test_remove_is_reachable_only_for_pure_removal_work():
    machine = load_module("requirements_run_remove", MACHINE / "run.py")

    assert machine._requirement_verdict([
        {"answer": "no", "needed": "remove"},
        {"answer": "no", "needed": "remove"},
    ]) == "remove"
    assert machine._requirement_verdict([
        {"answer": "yes", "needed": ""},
        {"answer": "no", "needed": "remove"},
    ]) == "change"
    assert machine._requirement_verdict([
        {"answer": "no", "needed": "add"},
        {"answer": "no", "needed": "remove"},
    ]) == "change"


def test_built_round_trip_writes_a_real_remove_verdict(tmp_path: Path):
    machine = load_module("requirements_run_remove_cli", MACHINE / "run.py")
    description = tmp_path / "description.md"
    description.write_text("The product must not emit debug output.\n", encoding="utf-8")
    built = tmp_path / "built"
    built.mkdir()
    (built / "impl.py").write_text("print('debug')\n", encoding="utf-8")
    work = tmp_path / "work"

    reading = machine.drive("quiet product", description, work, built)
    assert reading["status"] == "waiting_for_readers"
    obligation = json.loads((work / "obligations.json").read_text())["obligations"][0]
    requirement = {
        "candidate_id": obligation["id"],
        "requirement": "The product does not emit debug output.",
        "source": obligation["text"],
        "check": "No debug output is emitted.",
    }
    for index in (1, 2):
        write_json(work / f"oblige-{index}" / f"{obligation['id']}.json", requirement)

    merging = machine.drive("quiet product", description, work, built)
    assert merging["stopped"] == "merging"
    pair = json.loads((work / "pairs.json").read_text())["pairs"][0]
    for index in (1, 2):
        write_json(work / f"merge-{index}" / "pair.json", {
            "left": pair["left"], "right": pair["right"], "verdict": "merge",
            "surviving_requirement": requirement["requirement"], "why": "the same obligation",
        })

    splitting = machine.drive("quiet product", description, work, built)
    assert splitting["stopped"] == "splitting"
    write_json(work / "split-1" / "r1.json", {
        "id": "r1",
        "parts": [{"part_id": "r1.p1", "part": "The product does not emit debug output."}],
    })

    answering = machine.drive("quiet product", description, work, built)
    assert answering["stopped"] == "answering"
    for index in (1, 2):
        write_json(work / f"answer-{index}" / "r1.p1.json", {
            "part_id": "r1.p1", "answer": "no", "needed": "remove",
            "citations": [{"where": "impl.py", "line": 1, "text": "print('debug')"}],
            "looked_at": "impl.py emits the forbidden debug output.",
        })

    cli = subprocess.run([
        sys.executable, str(MACHINE / "run.py"), "--subject", "quiet product",
        "--description", str(description), "--work", str(work), "--built", str(built),
    ], capture_output=True, text=True, check=False)
    assert cli.returncode == 0, cli.stderr
    complete = json.loads(cli.stdout)
    assert complete["status"] == "complete"
    assert complete["remove"] == ["r1"]
    assert "## To remove" in Path(complete["document"]).read_text()
