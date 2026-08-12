from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "info-intake-machinery" / "scripts" / "start_intake.py"
SPEC = importlib.util.spec_from_file_location("start_intake", SCRIPT)
assert SPEC and SPEC.loader
START_INTAKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(START_INTAKE)
INTERVIEW_SCRIPT = ROOT / "skills" / "info-intake-machinery" / "scripts" / "projection_interview.py"
INTERVIEW_SPEC = importlib.util.spec_from_file_location("projection_interview", INTERVIEW_SCRIPT)
assert INTERVIEW_SPEC and INTERVIEW_SPEC.loader
PROJECTION_INTERVIEW = importlib.util.module_from_spec(INTERVIEW_SPEC)
INTERVIEW_SPEC.loader.exec_module(PROJECTION_INTERVIEW)
CODEX_RUNNER_SCRIPT = (
    ROOT / "skills" / "info-intake-machinery" / "scripts" / "run_projection_with_codex.py"
)
CODEX_RUNNER_SPEC = importlib.util.spec_from_file_location("run_projection_with_codex", CODEX_RUNNER_SCRIPT)
assert CODEX_RUNNER_SPEC and CODEX_RUNNER_SPEC.loader
CODEX_RUNNER = importlib.util.module_from_spec(CODEX_RUNNER_SPEC)
CODEX_RUNNER_SPEC.loader.exec_module(CODEX_RUNNER)


def test_empty_start_creates_one_resumable_intake_and_question(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    opening = "There is a new intake"

    first = START_INTAKE.drive(work, opening)
    before = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()}
    second = START_INTAKE.drive(work, opening)
    after = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()}

    assert first == second
    assert first["status"] == "needs_operator"
    assert first["question"] == START_INTAKE.OPENING_QUESTION
    assert before == after
    assert (work / "sources" / "source-000001.txt").read_text() == opening
    assert (work / "projections" / "projection-000001.txt").read_text() == opening
    ledger = [json.loads(line) for line in (work / "ledger.jsonl").read_text().splitlines()]
    assert [entry["event"] for entry in ledger] == [
        "source_projected",
        "operator_question_asked",
    ]


def test_changed_opening_cannot_rebind_existing_intake(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    START_INTAKE.drive(work, "There is a new intake")
    before = (work / "ledger.jsonl").read_bytes()

    result = START_INTAKE.drive(work, "Start another intake")

    assert result["status"] == "blocked"
    assert result["stopped"] == "input changed"
    assert (work / "ledger.jsonl").read_bytes() == before


def test_altered_ledger_fails_closed(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    START_INTAKE.drive(work, "There is a new intake")
    ledger_path = work / "ledger.jsonl"
    ledger_path.write_text(ledger_path.read_text().replace("source_projected", "source_hidden"))

    result = START_INTAKE.drive(work, "There is a new intake")

    assert result["status"] == "blocked"
    assert result["stopped"] == "invalid ledger"


def test_blank_opening_is_rejected_without_creating_state(tmp_path: Path) -> None:
    work = tmp_path / "intake"

    result = START_INTAKE.drive(work, "   ")

    assert result["status"] == "blocked"
    assert not work.exists()


def test_non_directory_work_path_fails_closed(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    work.write_text("occupied")

    result = START_INTAKE.drive(work, "There is a new intake")

    assert result["status"] == "blocked"
    assert result["stopped"] == "invalid work path"


def test_state_identity_must_match_the_ledger(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    START_INTAKE.drive(work, "There is a new intake")
    state_path = work / "intake-state.json"
    state = json.loads(state_path.read_text())
    state["intake_id"] = "intake-different"
    state_path.write_text(json.dumps(state))

    result = START_INTAKE.drive(work, "There is a new intake")

    assert result["status"] == "blocked"
    assert result["stopped"] == "invalid ledger"


def test_cli_exercises_the_same_empty_start_path(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    command = [sys.executable, str(SCRIPT), "--work", str(work), "--opening", "There is a new intake"]

    first = subprocess.run(command, check=False, text=True, capture_output=True)
    second = subprocess.run(command, check=False, text=True, capture_output=True)

    assert first.returncode == 4
    assert second.returncode == 4
    assert json.loads(first.stdout) == json.loads(second.stdout)


REAL_PURPOSE = (
    "the important thing the intake is for is the description in the red rectangles, but each "
    "description is related through its arrow to the element in the page underneath it came from"
)


def _sufficient_assessment() -> dict[str, object]:
    return {
        "schema_version": 1,
        "sufficient": "yes",
        "quote": REAL_PURPOSE,
        "reason": "The answer identifies the descriptions and their relationships as the content to preserve.",
        "clarifying_question": "",
        "reader": {"model": "test-reader", "harness": "pytest"},
    }


def _purpose_answers(
    *,
    sufficient: str = "yes",
    quote: str = REAL_PURPOSE,
    clarification: str = "What information or relationships must the AI-readable result preserve?",
) -> list[str]:
    reason = (
        "The answer identifies the descriptions and their relationships as the content to preserve."
        if sufficient == "yes"
        else "The answer does not identify what information must survive."
    )
    return [
        "test-reader",
        "pytest",
        sufficient,
        reason,
        quote if sufficient == "yes" else clarification,
    ]


def _run_purpose_interview(
    work: Path,
    answers: list[str] | None = None,
    messages: list[str] | None = None,
) -> dict[str, object]:
    remaining = iter(answers or _purpose_answers())
    return START_INTAKE.run_purpose_interview(
        work,
        input_fn=lambda _prompt: next(remaining),
        output_fn=(messages.append if messages is not None else lambda _message: None),
    )


def _advance_to_first_source(work: Path) -> None:
    opening = "There is a new intake"
    START_INTAKE.drive(work, opening)
    START_INTAKE.drive(work, opening, REAL_PURPOSE)
    result = _run_purpose_interview(work)
    assert result["stopped"] == "awaiting_first_source"


def _advance_to_frozen_image(work: Path, supplied: Path) -> dict[str, object]:
    supplied.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII="
    ))
    _advance_to_first_source(work)
    result = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    assert result["status"] == "ready_for_projection"
    assert result["source"]["media_type"] == "image/png"
    return result


def _projection_answers(
    *, invalid_status_first: bool = False, contract: int = 4,
) -> list[str]:
    element_status = ["ok", "readable"] if invalid_status_first else ["readable"]
    relationship_status = ["ok", "readable"] if invalid_status_first else ["readable"]
    first_obligation = ["yes"] if contract >= 3 else []
    second_obligation = ["yes"] if contract >= 3 else []
    required_relationship = (
        ["use_recorded_endpoint", "visually-connected-to", "origin", "element-000002"]
        if contract >= 3 else
        ["yes", "visually-connected-to", "element-000001", "element-000002"]
    )
    completed_element_scan = (
        ["no", *(["no"] * 15)] if contract >= 4 else ["no"]
    )
    return [
        "test-model", "pytest",
        "yes", "visible-text", "10", "20", "100", "120", *element_status,
        "A readable description", *first_obligation,
        "yes", "visible-target", "120", "20", "220", "120", "gap",
        "The target is obscured.", *second_obligation,
        *completed_element_scan,
        *required_relationship,
        *relationship_status, "The first element connects to the second.",
        "no",
    ]


def test_codex_projection_runner_derives_immutable_attachment_and_delimits_prompt(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "source.png"
    _advance_to_frozen_image(work, supplied)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)

    attachment, command = CODEX_RUNNER.load_request(work)
    argv = CODEX_RUNNER.build_codex_argv("/usr/local/bin/codex", work, attachment, command)

    assert attachment == work / "sources" / "source-000003"
    assert command[-1] == "--run-projection-interview"
    assert argv[argv.index("--image") + 1] == str(attachment)
    assert argv[-2] == "--"
    assert command[0] in argv[-1]
    assert "red rectangle" not in argv[-1]
    assert "arrow" not in argv[-1]


def test_codex_projection_runner_rejects_changed_frozen_source(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "source.png"
    _advance_to_frozen_image(work, supplied)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    (work / "sources" / "source-000003").write_bytes(b"changed")

    try:
        CODEX_RUNNER.load_request(work)
    except CODEX_RUNNER.LaunchError as error:
        assert str(error) == "the frozen first source is unavailable or has changed"
    else:
        raise AssertionError("changed source was accepted")


def test_projection_interview_enforces_choices_and_code_assembles_result(tmp_path: Path) -> None:
    answers = iter(_projection_answers(invalid_status_first=True))
    messages: list[str] = []
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    result = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="a" * 64,
        purpose=REAL_PURPOSE,
        input_fn=answer,
        output_fn=messages.append,
    )
    resumed = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="a" * 64,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: (_ for _ in ()).throw(AssertionError("already complete")),
        output_fn=messages.append,
    )

    assert result == resumed
    assert [item["status"] for item in result["elements"]] == ["readable", "gap"]
    assert result["relationships"][0]["status"] == "readable"
    assert result["relationships"][0]["from_id"] == "element-000001"
    assert result["relationships"][0]["to_id"] == "element-000002"
    assert result["relationship_obligations"] == [
        {
            "id": "obligation-000001", "element_id": "element-000001",
            "status": "resolved", "resolution": "relationship",
            "relationship_id": "relationship-000001",
        },
        {
            "id": "obligation-000002", "element_id": "element-000002",
            "status": "resolved", "resolution": "relationship",
            "relationship_id": "relationship-000001",
        },
    ]
    assert len(result["scan_regions"]) == 16
    assert all(region["status"] == "scanned" for region in result["scan_regions"])
    assert result["scan_regions"][0]["element_ids"] == [
        "element-000001", "element-000002",
    ]
    assert all(not region["element_ids"] for region in result["scan_regions"][1:])
    assert messages == [
        "Invalid answer: element_status: choose one of: readable, gap.",
        "Invalid answer: relationship_status: choose one of: readable, gap.",
    ]
    journal = [json.loads(line) for line in (tmp_path / "attempt" / "interview.jsonl").read_text().splitlines()]
    rejected = [entry for entry in journal if entry["event"] == "answer_recorded" and not entry["accepted"]]
    assert [entry["raw"] for entry in rejected] == ["ok", "ok"]
    purpose_questions = [
        entry["question"]
        for entry in journal
        if entry["event"] == "question_asked"
        and str(entry["question"]["id"]).startswith(("element_", "relationship_"))
    ]
    assert purpose_questions
    assert all(
        question["context"] == {"intake_purpose": REAL_PURPOSE}
        for question in purpose_questions
    )
    assert all(
        f"Intake purpose: {REAL_PURPOSE}" in prompt
        for prompt in prompts[2:]
    )
    assert journal[-1]["event"] == "interview_completed"


def test_spatial_traversal_rejects_element_anchor_outside_active_region(
    tmp_path: Path,
) -> None:
    answers = _projection_answers()
    answers.insert(4, "300")
    messages: list[str] = []

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="f" * 64,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: answers.pop(0),
        output_fn=messages.append,
    )

    assert projection["elements"][0]["scan_region_id"] == "region-r01-c01"
    assert messages[0] == (
        "Invalid answer: element_left: left coordinate 300 must be inside "
        "active region-r01-c01 horizontal bounds 0 through 249."
    )


def test_spatial_traversal_preserves_explicit_region_gap(tmp_path: Path) -> None:
    answers = iter([
        "test-model", "pytest",
        "gap", "The source is visibly occluded in this region.",
        *(["no"] * 15),
        "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="0" * 64,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    assert projection["elements"] == []
    assert projection["scan_regions"][0]["status"] == "gap"
    assert projection["scan_regions"][0]["gap_reason"] == (
        "The source is visibly occluded in this region."
    )
    assert all(
        region["status"] == "scanned"
        for region in projection["scan_regions"][1:]
    )


def test_relationship_obligation_routes_back_to_capture_visible_endpoint(
    tmp_path: Path,
) -> None:
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation", "10", "10", "100", "100", "readable",
        "Formula description", "yes",
        "no",
        "record_visible_endpoint",
        "dashboard field", "200", "10", "300", "100", "readable",
        "Conversion rate", "yes",
        "no",
        "use_recorded_endpoint", "arrow applies annotation to field",
        "origin", "element-000002", "readable",
        "The formula description applies to Conversion rate.",
        "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="c" * 64,
        purpose=REAL_PURPOSE,
        contract=3,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    assert [item["content"] for item in projection["elements"]] == [
        "Formula description", "Conversion rate",
    ]
    assert projection["relationships"] == [{
        "id": "relationship-000001",
        "kind": "arrow applies annotation to field",
        "from_id": "element-000001",
        "to_id": "element-000002",
        "status": "readable",
        "description": "The formula description applies to Conversion rate.",
        "gap_reason": "",
    }]
    assert all(
        item["status"] == "resolved"
        for item in projection["relationship_obligations"]
    )


def test_relationship_obligation_preserves_unreadable_endpoint_as_gap(
    tmp_path: Path,
) -> None:
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation", "10", "10", "100", "100", "readable",
        "Formula description", "yes",
        "no",
        "record_endpoint_gap", "arrow applies annotation to obscured target",
        "origin", "The arrow ends under an opaque overlay.",
        "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="d" * 64,
        purpose=REAL_PURPOSE,
        contract=3,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    relationship = projection["relationships"][0]
    assert relationship["status"] == "gap"
    assert relationship["participant_id"] == "element-000001"
    assert relationship["from_id"] == "element-000001"
    assert relationship["to_id"] is None
    assert relationship["gap_reason"] == "The arrow ends under an opaque overlay."
    assert projection["relationship_obligations"][0]["resolution"] == "gap"


def test_projection_interview_contract_one_remains_replayable(tmp_path: Path) -> None:
    attempt = tmp_path / "legacy-attempt"
    answers = iter(_projection_answers(contract=1))

    created = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256="b" * 64,
        purpose=REAL_PURPOSE,
        contract=1,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    replayed, _, _ = PROJECTION_INTERVIEW.validate(
        attempt,
        source_sha256="b" * 64,
        purpose=REAL_PURPOSE,
        contract=1,
    )

    assert replayed == created
    assert created["schema_version"] == 1
    journal = [json.loads(line) for line in (attempt / "interview.jsonl").read_text().splitlines()]
    assert all(
        "context" not in entry["question"]
        for entry in journal
        if entry["event"] == "question_asked"
    )


def test_projection_interview_contract_two_remains_replayable(tmp_path: Path) -> None:
    attempt = tmp_path / "contract-two-attempt"
    answers = iter(_projection_answers(contract=2))

    created = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256="e" * 64,
        purpose=REAL_PURPOSE,
        contract=2,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    replayed, _, _ = PROJECTION_INTERVIEW.validate(
        attempt,
        source_sha256="e" * 64,
        purpose=REAL_PURPOSE,
        contract=2,
    )

    assert replayed == created
    assert created["schema_version"] == 2
    assert "relationship_obligations" not in created


def test_projection_interview_contract_three_remains_replayable(tmp_path: Path) -> None:
    attempt = tmp_path / "contract-three-attempt"
    answers = iter(_projection_answers(contract=3))

    created = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256="1" * 64,
        purpose=REAL_PURPOSE,
        contract=3,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    replayed, _, _ = PROJECTION_INTERVIEW.validate(
        attempt,
        source_sha256="1" * 64,
        purpose=REAL_PURPOSE,
        contract=3,
    )

    assert replayed == created
    assert created["schema_version"] == 3
    assert "relationship_obligations" in created
    assert "scan_regions" not in created


def test_real_purpose_advances_to_first_source_and_resumes_without_duplication(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    opening = "There is a new intake"
    START_INTAKE.drive(work, opening)

    waiting = START_INTAKE.drive(work, opening, REAL_PURPOSE)
    assert waiting["status"] == "waiting_for_model"
    instruction = waiting["work"][0]["instruction"]
    assert "typed question currently displayed" in instruction
    assert waiting["work"][0]["command"][-1] == "--run-purpose-interview"
    assert all(word not in instruction for word in ("annotation", "color", "arrow", "dashboard"))
    completed = _run_purpose_interview(work)
    before = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()}
    resumed = START_INTAKE.drive(work, opening, REAL_PURPOSE)
    after = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()}

    assert completed == resumed
    assert completed["status"] == "needs_operator"
    assert completed["stopped"] == "awaiting_first_source"
    assert completed["question"] == START_INTAKE.FIRST_SOURCE_QUESTION
    assert before == after
    assert len((work / "ledger.jsonl").read_text().splitlines()) == 6
    assert (work / "sources" / "source-000002.txt").read_text() == REAL_PURPOSE


def test_cli_runs_the_same_typed_purpose_interview(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    START_INTAKE.drive(work, "There is a new intake")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    command = [
        sys.executable,
        str(SCRIPT),
        "--work",
        str(work),
        "--run-purpose-interview",
    ]

    completed = subprocess.run(
        command,
        input="\n".join(_purpose_answers()) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 4
    result = json.loads(completed.stdout)
    assert result["stopped"] == "awaiting_first_source"
    assert "Allowed values: yes, no" in completed.stderr


def test_empty_purpose_meaning_leads_to_one_model_clarification(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    opening = "There is a new intake"
    START_INTAKE.drive(work, opening)
    START_INTAKE.drive(work, opening, opening)
    result = _run_purpose_interview(work, _purpose_answers(sufficient="no"))

    assert result["status"] == "needs_operator"
    assert result["stopped"] == "clarifying_intake_purpose"
    assert result["question"] == {
        "id": "intake-purpose-clarification",
        "asks": "What information or relationships must the AI-readable result preserve?",
    }


def test_purpose_interview_rejects_non_source_quote_without_advancing(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    opening = "There is a new intake"
    START_INTAKE.drive(work, opening)
    START_INTAKE.drive(work, opening, REAL_PURPOSE)
    answers = _purpose_answers()
    answers[-1:] = ["a paraphrase", REAL_PURPOSE]
    messages: list[str] = []

    result = _run_purpose_interview(work, answers, messages)

    assert result["status"] == "needs_operator"
    assert result["stopped"] == "awaiting_first_source"
    assert messages == [
        "Invalid answer: quote: answer with an exact non-empty passage from the preserved purpose."
    ]
    ledger = [json.loads(line) for line in (work / "ledger.jsonl").read_text().splitlines()]
    assert ledger[4]["rejected_answer_count"] == 1


def test_changed_preserved_purpose_fails_closed(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    opening = "There is a new intake"
    START_INTAKE.drive(work, opening)
    START_INTAKE.drive(work, opening, REAL_PURPOSE)

    result = START_INTAKE.drive(work, opening, "A different purpose")

    assert result["status"] == "blocked"
    assert result["stopped"] == "purpose changed"


def test_purpose_interview_rejects_long_clarification_without_advancing(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    opening = "There is a new intake"
    START_INTAKE.drive(work, opening)
    START_INTAKE.drive(work, opening, opening)
    answers = _purpose_answers(sufficient="no")
    answers[-1:] = ["x" * 240 + "?", "What information must survive?"]
    messages: list[str] = []

    result = _run_purpose_interview(work, answers, messages)

    assert result["status"] == "needs_operator"
    assert result["stopped"] == "clarifying_intake_purpose"
    assert len(messages) == 1


def test_completed_result_must_remain_bound_to_ledger(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    opening = "There is a new intake"
    START_INTAKE.drive(work, opening)
    START_INTAKE.drive(work, opening, REAL_PURPOSE)
    _run_purpose_interview(work)
    state_path = work / "intake-state.json"
    result_path = work / "purpose-interview" / "assessment.json"
    changed = _sufficient_assessment()
    changed["reason"] = "A different reason that was never recorded in the ledger."
    result_path.write_text(json.dumps(changed))
    state = json.loads(state_path.read_text())
    state["assessment_result_sha256"] = START_INTAKE._digest_bytes(result_path.read_bytes())
    state_path.write_text(json.dumps(state))

    result = START_INTAKE.drive(work, opening, REAL_PURPOSE)

    assert result["status"] == "blocked"
    assert result["stopped"] == "invalid purpose interview"


def test_completed_question_must_follow_assessment(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    opening = "There is a new intake"
    START_INTAKE.drive(work, opening)
    START_INTAKE.drive(work, opening, REAL_PURPOSE)
    _run_purpose_interview(work)
    state_path = work / "intake-state.json"
    state = json.loads(state_path.read_text())
    state["phase"] = "clarifying_intake_purpose"
    state["waiting_for"] = "intake-purpose-clarification"
    state["question"] = {
        "id": "intake-purpose-clarification",
        "asks": "What else should survive?",
    }
    state_path.write_text(json.dumps(state))

    result = START_INTAKE.drive(work, opening, REAL_PURPOSE)

    assert result["status"] == "blocked"
    assert result["stopped"] == "invalid intake state"


def test_first_local_file_is_frozen_and_resumes_without_duplication(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "first-source.txt"
    content = b"source content\nwith structure\n"
    supplied.write_bytes(content)
    _advance_to_first_source(work)

    first = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    before = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()}
    resumed_with_source = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, supplied
    )
    resumed_without_origin = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    after = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()}

    assert first == resumed_with_source == resumed_without_origin
    assert first["status"] == "ready_for_projection"
    assert first["source"]["provided_path"] == str(supplied)
    assert first["source"]["resolved_path"] == str(supplied.resolve())
    assert first["source"]["filename"] == supplied.name
    assert first["source"]["adapter"] == {"name": "local_file", "version": 1}
    assert first["source"]["size_bytes"] == len(content)
    assert first["source"]["sha256"] == START_INTAKE._digest_bytes(content)
    assert first["source"]["media_type"] == "text/plain"
    assert (work / "sources" / "source-000003").read_bytes() == content
    assert before == after
    ledger = [json.loads(line) for line in (work / "ledger.jsonl").read_text().splitlines()]
    assert len(ledger) == 7
    assert ledger[-1]["event"] == "source_acquired"
    assert ledger[-1]["projection"]["status"] == "pending"


def test_missing_first_source_fails_without_changing_intake(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_first_source(work)
    before = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()}

    result = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, tmp_path / "missing.txt"
    )
    after = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()}

    assert result["status"] == "blocked"
    assert result["stopped"] == "source unavailable"
    assert before == after


def test_changed_first_source_fails_closed(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "first-source.txt"
    supplied.write_text("original")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    supplied.write_text("changed")

    result = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)

    assert result["status"] == "blocked"
    assert result["stopped"] == "source changed"


def test_same_content_from_different_origin_cannot_replace_occurrence(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("same")
    second.write_text("same")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, first)

    result = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, second)

    assert result["status"] == "blocked"
    assert result["stopped"] == "source origin changed"


def test_changed_frozen_copy_fails_closed(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "first.txt"
    supplied.write_text("original")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    (work / "sources" / "source-000003").write_text("changed")

    result = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)

    assert result["status"] == "blocked"
    assert result["stopped"] == "immutable source changed"


def test_source_is_not_silently_accepted_before_purpose_assessment(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "first.txt"
    supplied.write_text("source")
    START_INTAKE.drive(work, "There is a new intake")

    result = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, supplied
    )

    assert result["status"] == "blocked"
    assert result["stopped"] == "source not requested"
    assert not (work / "sources" / "source-000003").exists()


def test_frozen_source_record_cannot_redirect_its_stored_path(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "first.txt"
    supplied.write_text("source")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    state_path = work / "intake-state.json"
    state = json.loads(state_path.read_text())
    state["first_source"]["stored_path"] = "../outside"
    state_path.write_text(json.dumps(state))

    result = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)

    assert result["status"] == "blocked"
    assert result["stopped"] == "invalid ledger"


def test_projection_request_is_general_and_bound_to_frozen_image(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    frozen = _advance_to_frozen_image(work, tmp_path / "first.png")

    waiting = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    resumed = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)

    assert waiting == resumed
    assert waiting["status"] == "waiting_for_model"
    assert waiting["stopped"] == "interviewing_first_projection"
    assert waiting["work"][0]["attachments"] == [
        str((work / "sources" / "source-000003").resolve())
    ]
    instruction = waiting["work"][0]["instruction"]
    assert "typed question currently displayed" in instruction
    assert waiting["work"][0]["command"][-1] == "--run-projection-interview"
    assert all(word not in instruction.lower() for word in ("dashboard", "annotation", "color", "arrow"))
    ledger = [json.loads(line) for line in (work / "ledger.jsonl").read_text().splitlines()]
    assert len(ledger) == 8
    assert ledger[-1]["event"] == "model_projection_interview_started"
    assert ledger[-1]["source_sha256"] == frozen["source"]["sha256"]
    assert ledger[-1]["interview_contract"] == PROJECTION_INTERVIEW.CONTRACT


def test_source_and_projection_request_must_be_separate_atomic_actions(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "first.png"
    supplied.write_bytes(b"not acquired")
    _advance_to_first_source(work)

    result = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, supplied, project_source=True
    )

    assert result["status"] == "blocked"
    assert result["stopped"] == "source not yet frozen"
    assert not (work / "sources" / "source-000003").exists()
    assert len((work / "ledger.jsonl").read_text().splitlines()) == 6


def test_valid_projection_attempt_creates_immutable_unassessed_version(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    answers = iter(_projection_answers())

    accepted = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    before = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()}
    resumed = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    after = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()}

    assert accepted == resumed
    assert accepted["status"] == "ready_for_projection_assessment"
    assert accepted["projection"]["coverage"] == "unassessed"
    assert accepted["projection"]["element_count"] == 2
    assert accepted["projection"]["relationship_count"] == 1
    assert accepted["projection"]["gap_count"] == 1
    assert before == after
    projection = json.loads((work / accepted["projection"]["path"]).read_text())
    assert projection["reader"] == {"model": "test-model", "harness": "pytest"}
    assert [item["id"] for item in projection["elements"]] == [
        "element-000001", "element-000002"
    ]
    assert projection["relationships"][0]["from_id"] == "element-000001"
    assert projection["relationships"][0]["to_id"] == "element-000002"
    ledger = [json.loads(line) for line in (work / "ledger.jsonl").read_text().splitlines()]
    assert [entry["event"] for entry in ledger[-2:]] == [
        "model_projection_interview_completed", "projection_version_created"
    ]
    assert ledger[-2]["rejected_answer_count"] == 0


def test_projection_ledger_counts_spatial_traversal_gaps(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    answers = iter([
        "test-model", "pytest",
        "gap", "The source is visibly occluded in this region.",
        *(["no"] * 15),
        "no",
    ])

    accepted = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    assert accepted["projection"]["element_count"] == 0
    assert accepted["projection"]["relationship_count"] == 0
    assert accepted["projection"]["gap_count"] == 1
    resumed = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    assert resumed == accepted


def test_invalid_enum_answers_are_preserved_without_entering_projection(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    answers = iter(_projection_answers(invalid_status_first=True))
    messages: list[str] = []

    accepted = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )

    assert accepted["status"] == "ready_for_projection_assessment"
    projection = json.loads((work / accepted["projection"]["path"]).read_text())
    assert "ok" not in {item["status"] for item in projection["elements"]}
    assert "ok" not in {item["status"] for item in projection["relationships"]}
    journal_path = work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
    journal = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert [entry["raw"] for entry in journal if entry["event"] == "answer_recorded" and not entry["accepted"]] == ["ok", "ok"]
    assert len(messages) == 2
    ledger = [json.loads(line) for line in (work / "ledger.jsonl").read_text().splitlines()]
    assert ledger[-2]["rejected_answer_count"] == 2
    assert ledger[-2]["interview_sha256"] == START_INTAKE._digest_bytes(journal_path.read_bytes())


def test_cli_runs_the_same_typed_projection_interview(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    command = [
        sys.executable,
        str(SCRIPT),
        "--work",
        str(work),
        "--run-projection-interview",
    ]

    completed = subprocess.run(
        command,
        input="\n".join(_projection_answers()) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert result["status"] == "ready_for_projection_assessment"
    assert "Allowed values: readable, gap" in completed.stderr
    assert result["projection"]["coverage"] == "unassessed"


def test_changed_projection_version_fails_closed(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    answers = iter(_projection_answers())
    accepted = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    (work / accepted["projection"]["path"]).write_text("{}")

    result = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)

    assert result["status"] == "blocked"
    assert result["stopped"] == "immutable projection changed"


def test_visual_projection_adapter_fails_closed_for_other_media(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "first.txt"
    supplied.write_text("plain text")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    before = (work / "ledger.jsonl").read_bytes()

    result = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )

    assert result["status"] == "blocked"
    assert result["stopped"] == "projection adapter unavailable"
    assert (work / "ledger.jsonl").read_bytes() == before
