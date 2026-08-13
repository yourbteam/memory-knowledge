from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import shutil
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
CORRECTION_SCRIPT = (
    ROOT / "skills" / "info-intake-machinery" / "scripts" / "relationship_correction.py"
)
CORRECTION_SPEC = importlib.util.spec_from_file_location(
    "relationship_correction", CORRECTION_SCRIPT
)
assert CORRECTION_SPEC and CORRECTION_SPEC.loader
RELATIONSHIP_CORRECTION = importlib.util.module_from_spec(CORRECTION_SPEC)
CORRECTION_SPEC.loader.exec_module(RELATIONSHIP_CORRECTION)


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
    *, invalid_status_first: bool = False, contract: int = 6,
) -> list[str]:
    element_status = ["ok", "readable"] if invalid_status_first else ["readable"]
    relationship_status = ["ok", "readable"] if invalid_status_first else ["readable"]
    first_obligation = ["yes"] if contract >= 3 else []
    second_obligation = ["no"] if contract >= 6 else ["yes"] if contract >= 3 else []
    required_relationship = (
        ["use_recorded_endpoint", "visually-connected-to", "10", "20", "120", "20"]
        if contract >= 5 else
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
        *(["supported"] if contract >= 6 else []),
        *relationship_status, "The first element connects to the second.",
        "no",
    ]


def _verification_answers(
    relationship_count: int, *, verdict: str = "supported",
) -> list[str]:
    return [
        "independent-test-model", "pytest-fresh-reader",
        *[
            value
            for _ in range(relationship_count)
            for value in (verdict, "The frozen source visibly establishes this exact pair.")
        ],
    ]


def _gap_correction_answers() -> list[str]:
    return [
        "fresh-corrector", "pytest-correction", "preserve_gap",
        "No faithful visible endpoint can be recorded from this source.",
    ]


def _new_endpoint_correction_answers() -> list[str]:
    return [
        "fresh-corrector", "pytest-correction", "propose_replacement_endpoint", "target",
        "record_visible_element", "correct visible metric", "300", "0", "400", "100",
        "Correct metric", "350", "50", "The formula defines the correct visible metric.",
    ]


def _correction_fixture(tmp_path: Path) -> tuple[Path, str, Path, str, bytes, bytes]:
    candidate = {
        "schema_version": 7,
        "source_sha256": "a" * 64,
        "elements": [
            {"id": "element-000001", "kind": "annotation", "region": [0, 0, 100, 100], "status": "readable", "content": "Formula", "gap_reason": ""},
            {"id": "element-000002", "kind": "wrong metric", "region": [120, 0, 220, 100], "status": "readable", "content": "Wrong", "gap_reason": ""},
            {"id": "element-000003", "kind": "correct metric", "region": [240, 0, 340, 100], "status": "readable", "content": "Correct", "gap_reason": ""},
        ],
        "relationships": [{
            "id": "relationship-000001", "kind": "visible arrow", "from_id": "element-000001",
            "to_id": "element-000002", "origin_point": [50, 50], "target_point": [150, 50],
            "status": "readable", "description": "Formula defines wrong metric.", "gap_reason": "",
        }],
    }
    candidate_path = tmp_path / "projection.json"
    candidate_path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n")
    candidate_before = candidate_path.read_bytes()
    candidate_sha = RELATIONSHIP_CORRECTION._digest(candidate_before)
    verification = {
        "schema_version": 1,
        "candidate_sha256": candidate_sha,
        "reader": {"model": "fresh-verifier", "harness": "pytest"},
        "verdicts": [{
            "relationship_id": "relationship-000001", "verdict": "not_supported",
            "reason": "The arrow terminates at the correct metric instead.",
        }],
    }
    verification_path = tmp_path / "verification.json"
    verification_path.write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n")
    verification_before = verification_path.read_bytes()
    verification_sha = RELATIONSHIP_CORRECTION._digest(verification_before)
    return (
        candidate_path, candidate_sha, verification_path, verification_sha,
        candidate_before, verification_before,
    )


def test_rejected_relationship_can_propose_a_bound_replacement_without_overwriting(
    tmp_path: Path,
) -> None:
    candidate_path, candidate_sha, verification_path, verification_sha, candidate_before, verification_before = _correction_fixture(tmp_path)
    answers = iter([
        "fresh-corrector", "pytest-correction", "propose_replacement_endpoint", "target",
        "use_recorded_element", "element-000003", "250", "50",
        "Formula defines the correct metric.",
    ])

    result = RELATIONSHIP_CORRECTION.run(
        tmp_path / "correction", candidate_path=candidate_path,
        candidate_sha256=candidate_sha, verification_path=verification_path,
        verification_sha256=verification_sha, purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers), output_fn=lambda _message: None,
    )

    assert candidate_path.read_bytes() == candidate_before
    assert verification_path.read_bytes() == verification_before
    correction = result["corrections"][0]
    assert correction["original_relationship_id"] == "relationship-000001"
    assert correction["corrected_relationship"]["to_id"] == "element-000003"
    assert correction["corrected_relationship"]["binding_method"] == (
        "correction_selected_identity_and_containment"
    )
    assert correction["replacement_element"] == {
        "id": "element-000003", "created_by_correction": False,
    }
    verification_candidate = json.loads(
        (tmp_path / "correction" / "verification-candidate.json").read_text()
    )
    assert [item["id"] for item in verification_candidate["relationships"]] == [
        "relationship-000001-correction-000001"
    ]
    assert result["candidate_sha256"] == candidate_sha
    assert result["verification_sha256"] == verification_sha


def test_rejected_relationship_can_preserve_gap_and_rejected_choices_are_audited(
    tmp_path: Path,
) -> None:
    candidate_path, candidate_sha, verification_path, verification_sha, _, _ = _correction_fixture(tmp_path)
    answers = iter([
        "fresh-corrector", "pytest-correction", "invent_endpoint", "preserve_gap",
        "The source does not expose a faithful readable endpoint.",
    ])
    messages: list[str] = []

    result = RELATIONSHIP_CORRECTION.run(
        tmp_path / "correction", candidate_path=candidate_path,
        candidate_sha256=candidate_sha, verification_path=verification_path,
        verification_sha256=verification_sha, purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers), output_fn=messages.append,
    )

    assert result["corrections"] == [{
        "original_relationship_id": "relationship-000001",
        "action": "preserve_gap",
        "gap_reason": "The source does not expose a faithful readable endpoint.",
    }]
    assert messages == [
        "Invalid answer: correction_action: choose one of: propose_replacement_endpoint, preserve_gap."
    ]
    journal = [
        json.loads(line)
        for line in (tmp_path / "correction" / "interview.jsonl").read_text().splitlines()
    ]
    rejected = [entry for entry in journal if entry["event"] == "answer_recorded" and not entry["accepted"]]
    assert [entry["raw"] for entry in rejected] == ["invent_endpoint"]


def test_independent_verifier_skips_existing_relationship_gaps_without_losing_them(
    tmp_path: Path,
) -> None:
    candidate = {
        "elements": [],
        "relationships": [{
            "id": "relationship-gap", "status": "gap", "from_id": None, "to_id": None,
            "gap_reason": "The visible endpoint cannot be bound uniquely.",
        }],
    }
    candidate_path = tmp_path / "projection.json"
    candidate_path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n")
    candidate_sha = RELATIONSHIP_CORRECTION._digest(candidate_path.read_bytes())
    answers = iter(["fresh-reader", "pytest"])
    result = START_INTAKE.relationship_verification.run(
        tmp_path / "verification", candidate_path=candidate_path,
        candidate_sha256=candidate_sha, purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    assert result["verdicts"] == []
    assert candidate_path.read_text().count("relationship-gap") == 1


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
    assert "self-contained local controller" in argv[-1]
    assert "do not invoke task intake" in argv[-1]
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
    assert result["relationships"][0]["binding_method"] == "coordinate_unique_containment"
    assert result["relationships"][0]["origin_point"] == [10, 20]
    assert result["relationships"][0]["target_point"] == [120, 20]
    assert result["relationships"][0]["visual_verification"] == "supported"
    assert result["relationships"][0]["verified_obligation_id"] == "obligation-000001"
    assert result["relationship_obligations"] == [{
        "id": "obligation-000001", "element_id": "element-000001",
        "status": "resolved", "resolution": "relationship",
        "relationship_id": "relationship-000001",
    }]
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
    question_ids = {
        entry["question"]["id"]
        for entry in journal
        if entry["event"] == "question_asked"
    }
    assert "obligation_other_element" not in question_ids
    assert "relationship_from" not in question_ids
    assert "relationship_to" not in question_ids


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


def test_coordinate_binding_preserves_unmatched_endpoint_as_relationship_gap(
    tmp_path: Path,
) -> None:
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation", "10", "10", "100", "100", "readable",
        "Formula description", "yes",
        "yes", "dashboard field", "120", "10", "220", "100", "readable",
        "Conversion rate", "no",
        "no", *(["no"] * 15),
        "use_recorded_endpoint", "visible connector",
        "10", "10", "500", "500",
        "record_endpoint_gap", "No recorded element uniquely contains the visible target point.",
        "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="2" * 64,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    relationship = projection["relationships"][0]
    assert relationship["status"] == "gap"
    assert relationship["from_id"] == "element-000001"
    assert relationship["to_id"] is None
    assert relationship["origin_point"] == [10, 10]
    assert relationship["target_point"] == [500, 500]
    assert relationship["binding_issue"] == {
        "participant": "target",
        "point": [500, 500],
        "matching_element_ids": [],
        "reason": "no_unique_recorded_element",
    }
    assert projection["relationship_obligations"][0]["resolution"] == "gap"


def test_coordinate_binding_preserves_ambiguous_endpoint_as_relationship_gap(
    tmp_path: Path,
) -> None:
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation", "10", "10", "150", "150", "readable",
        "Formula description", "yes",
        "yes", "dashboard field", "50", "50", "200", "200", "readable",
        "Conversion rate", "no",
        "no", *(["no"] * 15),
        "use_recorded_endpoint", "visible connector",
        "75", "75",
        "record_endpoint_gap", "Two recorded elements overlap at the visible origin point.",
        "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="3" * 64,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    relationship = projection["relationships"][0]
    assert relationship["status"] == "gap"
    assert relationship["from_id"] is None
    assert relationship["binding_issue"]["matching_element_ids"] == [
        "element-000001", "element-000002",
    ]
    assert projection["relationship_obligations"][0]["resolution"] == "gap"


def test_coordinate_binding_can_capture_a_missing_visible_endpoint(
    tmp_path: Path,
) -> None:
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation", "10", "10", "100", "100", "readable",
        "Formula description", "yes",
        "yes", "unrelated field", "120", "10", "220", "100", "readable",
        "Unrelated value", "no",
        "no", *(["no"] * 15),
        "use_recorded_endpoint", "visible connector",
        "10", "10", "500", "500",
        "record_visible_endpoint",
        "dashboard field", "500", "500", "600", "600", "readable",
        "Conversion rate", "no",
        "500", "500", "supported", "readable",
        "The formula description applies to Conversion rate.",
        "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="4" * 64,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    assert len(projection["elements"]) == 3
    assert projection["elements"][2]["capture_scope"] == "relationship_endpoint"
    relationship = projection["relationships"][0]
    assert relationship["from_id"] == "element-000001"
    assert relationship["to_id"] == "element-000003"
    assert relationship["origin_point"] == [10, 10]
    assert relationship["target_point"] == [500, 500]
    assert all(
        obligation["status"] == "resolved"
        for obligation in projection["relationship_obligations"]
    )


def test_visual_verdict_blocks_unsupported_pair_from_readable_projection(
    tmp_path: Path,
) -> None:
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation", "10", "10", "100", "100", "readable",
        "Formula description", "yes",
        "yes", "dashboard field", "120", "10", "220", "100", "readable",
        "Unrelated value", "no",
        "no", *(["no"] * 15),
        "use_recorded_endpoint", "visible connector",
        "10", "10", "120", "10",
        "not_supported", "record_endpoint_gap",
        "The visible connector does not join the proposed participants.",
        "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="7" * 64,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    relationship = projection["relationships"][0]
    assert relationship["status"] == "gap"
    assert relationship["description"] == ""
    assert relationship["visual_verification"] == "not_supported"
    assert relationship["verification_issue"]["reason"] == (
        "visible_connection_not_supported"
    )
    assert projection["relationship_obligations"][0]["resolution"] == "gap"


def test_visual_verdict_preserves_unreadable_connection_as_gap(
    tmp_path: Path,
) -> None:
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation", "10", "10", "100", "100", "readable",
        "Formula description", "yes",
        "yes", "dashboard field", "120", "10", "220", "100", "readable",
        "Conversion rate", "no",
        "no", *(["no"] * 15),
        "use_recorded_endpoint", "visible connector",
        "10", "10", "120", "10",
        "unreadable", "The connector passes behind an opaque overlay.",
        "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="8" * 64,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    relationship = projection["relationships"][0]
    assert relationship["status"] == "gap"
    assert relationship["visual_verification"] == "unreadable"
    assert relationship["gap_reason"] == (
        "The connector passes behind an opaque overlay."
    )


def test_supported_pair_resolves_only_the_current_relationship_obligation(
    tmp_path: Path,
) -> None:
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation", "10", "10", "100", "100", "readable",
        "Formula description", "yes",
        "yes", "dashboard field", "120", "10", "220", "100", "readable",
        "Conversion rate", "yes",
        "no", *(["no"] * 15),
        "use_recorded_endpoint", "visible connector",
        "10", "10", "120", "10", "supported", "readable",
        "The annotation applies to the field.",
        "use_recorded_endpoint", "visible connector",
        "120", "10", "10", "10", "supported", "readable",
        "The field is explained by the annotation.",
        "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="9" * 64,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    assert [item["relationship_id"] for item in projection["relationship_obligations"]] == [
        "relationship-000001", "relationship-000002",
    ]
    assert [item["verified_obligation_id"] for item in projection["relationships"]] == [
        "obligation-000001", "obligation-000002",
    ]


def test_visual_verdict_is_code_constrained_to_three_values(tmp_path: Path) -> None:
    answers = _projection_answers()
    verdict_index = answers.index("supported")
    answers.insert(verdict_index, "maybe")
    messages: list[str] = []

    PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="a" * 64,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: answers.pop(0),
        output_fn=messages.append,
    )

    assert messages == [
        (
            "Invalid answer: relationship_visual_verdict: choose one of: "
            "supported, not_supported, unreadable."
        )
    ]


def test_coordinate_binding_refuses_participants_that_omit_the_required_element(
    tmp_path: Path,
) -> None:
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation", "10", "10", "70", "70", "readable",
        "Formula description", "yes",
        "yes", "dashboard field", "80", "10", "140", "70", "readable",
        "Correct target", "no",
        "yes", "unrelated field", "150", "10", "220", "70", "readable",
        "Unrelated value", "no",
        "no", *(["no"] * 15),
        "use_recorded_endpoint", "visible connector",
        "80", "10", "150", "10",
        "record_endpoint_gap", "The submitted pair omits the element whose relationship is required.",
        "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="6" * 64,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    relationship = projection["relationships"][0]
    assert relationship["status"] == "gap"
    assert relationship["binding_issue"] == {
        "participant": "relationship",
        "origin_id": "element-000002",
        "target_id": "element-000003",
        "required_element_id": "element-000001",
        "reason": "required_element_not_bound",
    }
    assert projection["relationship_obligations"][0]["resolution"] == "gap"


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


def test_projection_interview_contract_four_remains_replayable(tmp_path: Path) -> None:
    attempt = tmp_path / "contract-four-attempt"
    answers = iter(_projection_answers(contract=4))

    created = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256="5" * 64,
        purpose=REAL_PURPOSE,
        contract=4,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    replayed, _, _ = PROJECTION_INTERVIEW.validate(
        attempt,
        source_sha256="5" * 64,
        purpose=REAL_PURPOSE,
        contract=4,
    )

    assert replayed == created
    assert created["schema_version"] == 4
    assert "scan_regions" in created
    assert "binding_method" not in created["relationships"][0]


def test_projection_interview_contract_five_remains_replayable(tmp_path: Path) -> None:
    attempt = tmp_path / "contract-five-attempt"
    answers = iter(_projection_answers(contract=5))

    created = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256="6" * 64,
        purpose=REAL_PURPOSE,
        contract=5,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    replayed, _, _ = PROJECTION_INTERVIEW.validate(
        attempt,
        source_sha256="6" * 64,
        purpose=REAL_PURPOSE,
        contract=5,
    )

    assert replayed == created
    assert created["schema_version"] == 5
    assert created["relationships"][0]["binding_method"] == (
        "coordinate_unique_containment"
    )
    assert "visual_verification" not in created["relationships"][0]


def test_projection_interview_contract_six_remains_replayable(tmp_path: Path) -> None:
    attempt = tmp_path / "contract-six-attempt"
    answers = iter(_projection_answers(contract=6))

    created = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256="7" * 64,
        purpose=REAL_PURPOSE,
        contract=6,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    replayed, _, _ = PROJECTION_INTERVIEW.validate(
        attempt,
        source_sha256="7" * 64,
        purpose=REAL_PURPOSE,
        contract=6,
    )

    assert replayed == created
    assert created["schema_version"] == 6
    assert created["relationships"][0]["visual_verification"] == "supported"
    assert "independent_visual_verification" not in created["relationships"][0]


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

    waiting = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    assert waiting["stopped"] == "verifying_first_projection"
    verification_answers = iter(_verification_answers(1))
    accepted = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verification_answers),
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

    waiting = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    assert waiting["stopped"] == "verifying_first_projection"
    verification_answers = iter(_verification_answers(0))
    accepted = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verification_answers),
        output_fn=lambda _message: None,
    )

    assert accepted["projection"]["element_count"] == 0
    assert accepted["projection"]["relationship_count"] == 0
    assert accepted["projection"]["gap_count"] == 1
    resumed = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    assert resumed == accepted


def test_independent_reader_turns_unsupported_proposal_into_a_gap(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    producer_answers = iter(_projection_answers())
    waiting = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(producer_answers),
        output_fn=lambda _message: None,
    )
    candidate_path = work / "projection-interviews" / "attempt-000001" / "projection.json"
    candidate_before = candidate_path.read_bytes()

    verifier_answers = iter(_verification_answers(1, verdict="not_supported"))
    correcting = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verifier_answers),
        output_fn=lambda _message: None,
    )
    correction_answers = iter(_gap_correction_answers())
    accepted = START_INTAKE.run_relationship_correction(
        work,
        input_fn=lambda _prompt: next(correction_answers),
        output_fn=lambda _message: None,
    )

    assert waiting["stopped"] == "verifying_first_projection"
    assert correcting["stopped"] == "correcting_rejected_relationships"
    assert candidate_path.read_bytes() == candidate_before
    candidate = json.loads(candidate_before)
    projection = json.loads((work / accepted["projection"]["path"]).read_text())
    assert candidate["relationships"][0]["status"] == "readable"
    assert projection["relationships"][0]["status"] == "gap"
    assert projection["relationships"][0]["description"] == ""
    assert projection["relationships"][0]["independent_visual_verification"]["verdict"] == (
        "not_supported"
    )
    assert projection["relationships"][0]["correction_outcome"]["action"] == "preserve_gap"
    assert accepted["projection"]["gap_count"] == 2


def test_supported_correction_replaces_final_endpoint_and_preserves_all_prior_artifacts(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    producer_answers = iter(_projection_answers())
    START_INTAKE.run_first_projection_interview(
        work, input_fn=lambda _prompt: next(producer_answers), output_fn=lambda _message: None,
    )
    candidate_path = work / "projection-interviews" / "attempt-000001" / "projection.json"
    candidate_before = candidate_path.read_bytes()
    verifier_answers = iter(_verification_answers(1, verdict="not_supported"))
    correcting = START_INTAKE.run_first_projection_verification(
        work, input_fn=lambda _prompt: next(verifier_answers), output_fn=lambda _message: None,
    )
    _, correction_command = CODEX_RUNNER.load_request(work)
    original_verification_path = (
        work / "projection-verifications" / "attempt-000001" / "verification.json"
    )
    original_verification_before = original_verification_path.read_bytes()
    correction_answers = iter(_new_endpoint_correction_answers())

    verifying = START_INTAKE.run_relationship_correction(
        work, input_fn=lambda _prompt: next(correction_answers), output_fn=lambda _message: None,
    )
    _, correction_verification_command = CODEX_RUNNER.load_request(work)
    correction_path = work / "relationship-corrections" / "attempt-000001" / "corrections.json"
    correction_before = correction_path.read_bytes()
    correction_verifier_answers = iter(_verification_answers(1))
    accepted = START_INTAKE.run_relationship_correction_verification(
        work,
        input_fn=lambda _prompt: next(correction_verifier_answers),
        output_fn=lambda _message: None,
    )

    assert correcting["stopped"] == "correcting_rejected_relationships"
    assert correction_command[-1] == "--run-relationship-correction"
    assert verifying["stopped"] == "verifying_relationship_corrections"
    assert correction_verification_command[-1] == "--run-correction-verification"
    assert candidate_path.read_bytes() == candidate_before
    assert original_verification_path.read_bytes() == original_verification_before
    assert correction_path.read_bytes() == correction_before
    projection = json.loads((work / accepted["projection"]["path"]).read_text())
    relationship = projection["relationships"][0]
    assert relationship["id"] == "relationship-000001"
    assert relationship["to_id"] == "correction-element-000001"
    assert relationship["status"] == "readable"
    assert relationship["independent_visual_verification"]["verdict"] == "not_supported"
    assert relationship["correction_outcome"]["independent_visual_verification"]["verdict"] == (
        "supported"
    )
    assert accepted["projection"]["element_count"] == 3
    assert accepted["projection"]["gap_count"] == 1
    ledger = [json.loads(line) for line in (work / "ledger.jsonl").read_text().splitlines()]
    assert ledger[-2]["correction_result_sha256"]
    assert ledger[-2]["correction_verification_result_sha256"]


def test_invalid_enum_answers_are_preserved_without_entering_projection(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    answers = iter(_projection_answers(invalid_status_first=True))
    messages: list[str] = []

    waiting = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )
    assert waiting["stopped"] == "verifying_first_projection"
    verification_answers = iter(_verification_answers(1))
    accepted = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verification_answers),
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

    assert completed.returncode == 2
    result = json.loads(completed.stdout)
    assert result["stopped"] == "verifying_first_projection"
    verification_command = [
        sys.executable,
        str(SCRIPT),
        "--work",
        str(work),
        "--run-projection-verification",
    ]
    verified = subprocess.run(
        verification_command,
        input="\n".join(_verification_answers(1)) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    assert verified.returncode == 0
    verified_result = json.loads(verified.stdout)
    assert verified_result["status"] == "ready_for_projection_assessment"
    assert "Allowed values: readable, gap" in completed.stderr
    assert verified_result["projection"]["coverage"] == "unassessed"


def test_changed_projection_version_fails_closed(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    answers = iter(_projection_answers())
    waiting = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    assert waiting["stopped"] == "verifying_first_projection"
    verification_answers = iter(_verification_answers(1))
    accepted = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verification_answers),
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


def test_all_known_gaps_become_one_operator_question_round_without_overwriting(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    producer_answers = iter([
        "test-model", "pytest",
        "yes", "visible-text", "10", "20", "100", "120", "readable",
        "A readable description", "yes",
        "yes", "visible-target", "120", "20", "220", "120", "gap",
        "The first target is obscured.", "no",
        "yes", "another-visible-target", "10", "130", "100", "220", "gap",
        "The second target is obscured.", "no",
        "no", *(["no"] * 15),
        "use_recorded_endpoint", "visually-connected-to", "10", "20", "120", "20",
        "supported", "readable", "The description connects to the first target.", "no",
    ])
    START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(producer_answers),
        output_fn=lambda _message: None,
    )
    verification_answers = iter(_verification_answers(1))
    recorded = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verification_answers),
        output_fn=lambda _message: None,
    )
    original_projection = work / recorded["projection"]["path"]
    original_projection_before = original_projection.read_bytes()

    requested = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, clarify_gap=True,
    )
    attachment, command = CODEX_RUNNER.load_request(work)
    argv = CODEX_RUNNER.build_codex_argv(
        "/usr/local/bin/codex", work, attachment, command,
    )
    question_answers = iter([
        "fresh-questioner",
        "pytest-gap-question",
        "What exact information is hidden by the first obscured target?",
        "What exact information is hidden by the second obscured target?",
    ])
    waiting = START_INTAKE.run_gap_clarification(
        work,
        input_fn=lambda _prompt: next(question_answers),
        output_fn=lambda _message: None,
    )

    assert requested["stopped"] == "formulating_gap_question_round"
    assert command[-1] == "--run-gap-clarification"
    assert argv[argv.index("--image") + 1] == str(work / "sources" / "source-000003")
    assert "each code-bound gap" in argv[-1]
    assert waiting["status"] == "needs_operator"
    assert waiting["stopped"] == "awaiting_gap_answers"
    assert waiting["answered_question_count"] == 0
    assert waiting["question_count"] == 2
    assert waiting["question"]["answers_gap"]["id"] == "element-000002"
    assert "questions" not in waiting
    state = json.loads((work / "intake-state.json").read_text())
    assert [item["answers_gap"]["id"] for item in state["questions"]] == [
        "element-000002", "element-000003",
    ]
    assert [item["id"] for item in state["questions"]] == [
        "gap-clarification-answer-000001",
        "gap-clarification-answer-000002",
    ]
    ledger_before_empty = (work / "ledger.jsonl").read_bytes()
    empty_answer = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, gap_answer="   ",
    )
    assert empty_answer["status"] == "blocked"
    assert empty_answer["stopped"] == "gap answer required"
    assert (work / "ledger.jsonl").read_bytes() == ledger_before_empty

    first_answer_text = "The first target contains $100."
    second_question = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, gap_answer=first_answer_text,
    )
    resumed_second = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    assert second_question == resumed_second
    assert second_question["status"] == "needs_operator"
    assert second_question["answered_question_count"] == 1
    assert second_question["question_count"] == 2
    assert second_question["question"]["answers_gap"]["id"] == "element-000003"
    assert "questions" not in second_question
    assert (work / "sources" / "source-000004.txt").read_text() == first_answer_text
    assert (work / "projections" / "source-000004-v1.txt").read_text() == first_answer_text

    second_answer_text = "The second target contains $200."
    completed = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, gap_answer=second_answer_text,
    )
    resumed_completed = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE,
    )
    assert completed == resumed_completed
    assert completed["status"] == "ready_for_projection_assessment"
    assert completed["stopped"] == "gap_question_round_answered"
    assert completed["answered_question_count"] == 2
    assert completed["question_count"] == 2
    assert (work / "sources" / "source-000005.txt").read_text() == second_answer_text
    assert (work / "projections" / "source-000005-v1.txt").read_text() == second_answer_text
    assert original_projection.read_bytes() == original_projection_before

    ledger = [json.loads(line) for line in (work / "ledger.jsonl").read_text().splitlines()]
    assert [item["event"] for item in ledger[-8:]] == [
        "model_gap_question_round_requested",
        "model_gap_question_round_completed",
        "operator_question_round_prepared",
        "operator_question_asked",
        "source_projected",
        "operator_question_asked",
        "source_projected",
        "operator_question_round_answered",
    ]
    assert ledger[-4]["source"]["answers_question"] == "gap-clarification-answer-000001"
    assert ledger[-4]["source"]["answers_gap"]["id"] == "element-000002"
    assert ledger[-2]["source"]["answers_question"] == "gap-clarification-answer-000002"
    assert ledger[-2]["source"]["answers_gap"]["id"] == "element-000003"

    assessment_requested = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        assess_gap_answers=True,
    )
    assessment_attachment, assessment_command = CODEX_RUNNER.load_request(work)
    assessment_argv = CODEX_RUNNER.build_codex_argv(
        "/usr/local/bin/codex", work, assessment_attachment, assessment_command,
    )
    assessment_answers = iter([
        "fresh-assessor",
        "pytest-gap-answer-assessment",
        "maybe",
        "resolves_gap",
        "The first answer supplies the exact hidden value requested by its question.",
        "does_not_resolve_gap",
        "The second answer repeats a value but does not identify the obscured target.",
    ])
    assessed = START_INTAKE.run_gap_answer_assessment(
        work,
        input_fn=lambda _prompt: next(assessment_answers),
        output_fn=lambda _message: None,
    )
    resumed_assessment = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE,
    )

    assert assessment_requested["status"] == "waiting_for_model"
    assert assessment_requested["stopped"] == "assessing_gap_answers"
    assert assessment_command[-1] == "--run-gap-answer-assessment"
    assert assessment_argv[assessment_argv.index("--image") + 1] == str(
        work / "sources" / "source-000003"
    )
    assert "each code-bound preserved answer" in assessment_argv[-1]
    assert assessed == resumed_assessment
    assert assessed["status"] == "ready_for_projection_assessment"
    assert assessed["stopped"] == "gap_answer_assessment_recorded"
    assert [item["verdict"] for item in assessed["assessments"]] == [
        "resolves_gap", "does_not_resolve_gap",
    ]
    assert [item["gap"]["id"] for item in assessed["assessments"]] == [
        "element-000002", "element-000003",
    ]
    assert original_projection.read_bytes() == original_projection_before
    assessment_state = json.loads((work / "intake-state.json").read_text())
    bindings, binding_error = START_INTAKE._gap_answer_assessment_bindings(
        work, assessment_state,
    )
    assert binding_error is None and bindings is not None
    valid_result = {
        "assessments": assessed["assessments"],
    }
    missing = json.loads(json.dumps(valid_result))
    missing["assessments"].pop()
    reordered = json.loads(json.dumps(valid_result))
    reordered["assessments"].reverse()
    invented = json.loads(json.dumps(valid_result))
    invented["assessments"][0]["question_id"] = "invented-question"
    unsupported = json.loads(json.dumps(valid_result))
    unsupported["assessments"][0]["verdict"] = "maybe"
    for changed in (missing, reordered, invented, unsupported):
        assert START_INTAKE._validate_gap_answer_assessment_shape(
            changed, bindings,
        ) is not None

    answer_tamper = tmp_path / "answer-tamper"
    shutil.copytree(work, answer_tamper)
    answer_tamper_ledger = (answer_tamper / "ledger.jsonl").read_bytes()
    (answer_tamper / "projections" / "source-000004-v1.txt").write_text("changed")
    tampered_answer = START_INTAKE.drive(
        answer_tamper, "There is a new intake", REAL_PURPOSE,
    )
    assert tampered_answer["status"] == "blocked"
    assert "answer 1" in tampered_answer["why"]
    assert (answer_tamper / "ledger.jsonl").read_bytes() == answer_tamper_ledger

    assessment_path = (
        work / "gap-answer-assessments" / "round-000001" / "assessment.json"
    )
    persisted_result = json.loads(assessment_path.read_text())
    persisted_variants = {}
    for name in ("missing", "reordered", "invented", "altered", "unsupported"):
        persisted_variants[name] = json.loads(json.dumps(persisted_result))
    persisted_variants["missing"]["assessments"].pop()
    persisted_variants["reordered"]["assessments"].reverse()
    persisted_variants["invented"]["assessments"][0][
        "question_id"
    ] = "invented-question"
    persisted_variants["altered"]["assessments"][0][
        "reason"
    ] = "changed reason"
    persisted_variants["unsupported"]["assessments"][0]["verdict"] = "maybe"
    for name, changed in persisted_variants.items():
        result_tamper = tmp_path / f"result-{name}-tamper"
        shutil.copytree(work, result_tamper)
        ledger_before_result_tamper = (result_tamper / "ledger.jsonl").read_bytes()
        tampered_assessment_path = (
            result_tamper
            / "gap-answer-assessments"
            / "round-000001"
            / "assessment.json"
        )
        tampered_assessment_path.write_text(json.dumps(changed, indent=2, sort_keys=True) + "\n")
        tampered_result = START_INTAKE.drive(
            result_tamper, "There is a new intake", REAL_PURPOSE,
        )
        assert tampered_result["status"] == "blocked"
        assert tampered_result["stopped"] == "invalid gap answer assessment"
        assert (
            result_tamper / "ledger.jsonl"
        ).read_bytes() == ledger_before_result_tamper


def test_question_round_shape_rejects_missing_duplicate_reordered_or_invented_questions() -> None:
    gaps = [
        {
            "projection_sha256": "a" * 64,
            "collection": "elements",
            "kind": "element",
            "id": f"element-{index:06d}",
            "record_sha256": str(index) * 64,
        }
        for index in (1, 2)
    ]
    questions = [
        {
            "id": f"gap-clarification-answer-{index:06d}",
            "asks": f"Question {index}?",
            "answers_gap": {
                key: gaps[index - 1][key]
                for key in ("projection_sha256", "collection", "kind", "id", "record_sha256")
            },
        }
        for index in (1, 2)
    ]

    assert START_INTAKE._validate_question_round_shape(
        {"questions": questions[:1]}, gaps
    ) is not None
    duplicate = json.loads(json.dumps(questions))
    duplicate[1]["id"] = duplicate[0]["id"]
    assert START_INTAKE._validate_question_round_shape(
        {"questions": duplicate}, gaps
    ) is not None
    assert START_INTAKE._validate_question_round_shape(
        {"questions": list(reversed(questions))}, gaps
    ) is not None
    invented = json.loads(json.dumps(questions))
    invented[1]["answers_gap"]["id"] = "element-invented"
    assert START_INTAKE._validate_question_round_shape(
        {"questions": invented}, gaps
    ) is not None


def _gap_resolution_fixture(tmp_path: Path) -> dict[str, object]:
    relationship = {
        "id": "relationship-000001",
        "kind": "annotation_arrow",
        "from_id": None,
        "to_id": None,
        "origin_point": [100, 100],
        "target_point": [700, 100],
        "status": "gap",
        "description": "",
        "gap_reason": "origin point matches more than one readable element",
        "binding_issue": {
            "participant": "origin",
            "matching_element_ids": ["element-000001", "element-000002"],
        },
    }
    projection = {
        "schema_version": 1,
        "source_sha256": "frozen-image",
        "elements": [
            {"id": "element-000001", "kind": "callout", "region": [0, 0, 300, 300], "status": "readable", "content": "specific callout"},
            {"id": "element-000002", "kind": "section", "region": [0, 0, 500, 500], "status": "readable", "content": "whole section"},
            {"id": "element-000003", "kind": "field", "region": [600, 0, 800, 200], "status": "readable", "content": "May 16 · ACH"},
        ],
        "relationships": [relationship],
    }
    projection_path = tmp_path / "projection.json"
    projection_path.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n")
    projection_sha256 = START_INTAKE._digest_bytes(projection_path.read_bytes())
    record_sha256 = START_INTAKE._digest_bytes(
        json.dumps(relationship, sort_keys=True, separators=(",", ":")).encode()
    )
    gap = {
        "projection_sha256": projection_sha256,
        "collection": "relationships",
        "kind": "relationship_binding_gap",
        "id": relationship["id"],
        "record_id": relationship["id"],
        "record_sha256": record_sha256,
        "record": relationship,
    }
    clarification = {
        "schema_version": 1,
        "gap": gap,
        "question": {
            "id": "gap-question-000001",
            "asks": "Does the answer point to the callout or the whole section?",
            "answers_gap": {
                key: gap[key]
                for key in ("projection_sha256", "collection", "kind", "id", "record_sha256")
            },
        },
    }
    clarification_path = tmp_path / "clarification.json"
    clarification_path.write_text(json.dumps(clarification, indent=2, sort_keys=True) + "\n")
    answer_path = tmp_path / "answer.txt"
    answer_path.write_text("the answer points to the specific element, not the whole section")
    answer_projection_path = tmp_path / "answer-projection.txt"
    answer_projection_path.write_bytes(answer_path.read_bytes())
    return {
        "projection_path": projection_path,
        "projection_sha256": projection_sha256,
        "clarification_path": clarification_path,
        "clarification_sha256": START_INTAKE._digest_bytes(clarification_path.read_bytes()),
        "answer_source_path": answer_path,
        "answer_source_sha256": START_INTAKE._digest_bytes(answer_path.read_bytes()),
        "answer_projection_path": answer_projection_path,
        "answer_projection_sha256": START_INTAKE._digest_bytes(answer_projection_path.read_bytes()),
    }


def test_gap_resolution_enforces_choices_and_endpoint_containment(tmp_path: Path) -> None:
    inputs = _gap_resolution_fixture(tmp_path)
    attempt = tmp_path / "resolution"
    answers = iter([
        "fresh-resolver", "pytest-resolution", "maybe", "resolves_gap",
        "The answer selects the specific callout.", "element-000001",
        "use_recorded_element", "element-000003", "700", "300", "100",
        "The callout arrow identifies May 16 · ACH.",
    ])
    messages: list[str] = []

    result = START_INTAKE.gap_resolution.run(
        attempt,
        **inputs,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )
    candidate = json.loads((attempt / "verification-candidate.json").read_text())
    journal = [json.loads(line) for line in (attempt / "interview.jsonl").read_text().splitlines()]

    assert result["verdict"] == "resolves_gap"
    assert candidate["relationships"][0]["from_id"] == "element-000001"
    assert candidate["relationships"][0]["to_id"] == "element-000003"
    assert candidate["relationships"][0]["target_point"] == [700, 100]
    assert sum(item["event"] == "answer_recorded" and not item["accepted"] for item in journal) == 2
    assert "choose one of" in messages[0]
    assert "falls outside selected bounds" in messages[1]


def test_non_resolving_answer_produces_no_admissible_relationship(
    tmp_path: Path,
) -> None:
    inputs = _gap_resolution_fixture(tmp_path)
    attempt = tmp_path / "resolution"
    answers = iter([
        "fresh-resolver",
        "pytest-resolution",
        "does_not_resolve_gap",
        "The answer does not select either recorded candidate.",
    ])

    result = START_INTAKE.gap_resolution.run(
        attempt,
        **inputs,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    candidate = json.loads((attempt / "verification-candidate.json").read_text())

    assert result["verdict"] == "does_not_resolve_gap"
    assert candidate["relationships"] == []
    assert candidate["elements"] == json.loads(inputs["projection_path"].read_text())["elements"]


def test_independent_gap_resolution_verdict_controls_admission(tmp_path: Path) -> None:
    inputs = _gap_resolution_fixture(tmp_path)
    attempt = tmp_path / "resolution"
    answers = iter([
        "fresh-resolver", "pytest-resolution", "resolves_gap",
        "The answer selects the specific callout.", "element-000001",
        "use_recorded_element", "element-000003", "700", "100",
        "The callout arrow identifies May 16 · ACH.",
    ])
    START_INTAKE.gap_resolution.run(
        attempt,
        **inputs,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    verification_answers = iter([
        "fresh-verifier", "pytest-verification", "supported",
        "The answer selects the nested callout and both arrow endpoints are visible.",
    ])
    verification = START_INTAKE.gap_resolution_verification.run(
        tmp_path / "verification",
        candidate_path=attempt / "verification-candidate.json",
        candidate_sha256=START_INTAKE._digest_bytes((attempt / "verification-candidate.json").read_bytes()),
        resolution_path=attempt / "resolution.json",
        resolution_sha256=START_INTAKE._digest_bytes((attempt / "resolution.json").read_bytes()),
        clarification_path=inputs["clarification_path"],
        clarification_sha256=inputs["clarification_sha256"],
        answer_path=inputs["answer_source_path"],
        answer_sha256=inputs["answer_source_sha256"],
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(verification_answers),
        output_fn=lambda _message: None,
    )

    assert verification["verdict"] == "supported"
    assert verification["reader"] == {
        "model": "fresh-verifier",
        "harness": "pytest-verification",
    }


def test_gap_resolution_reuses_spatially_matching_record_instead_of_duplicating(
    tmp_path: Path,
) -> None:
    inputs = _gap_resolution_fixture(tmp_path)
    attempt = tmp_path / "resolution"
    answers = iter([
        "fresh-resolver", "pytest-resolution", "resolves_gap",
        "The answer selects the specific callout.", "element-000001",
        "record_visible_element", "field", "600", "0", "800", "200",
        "May 16 · ACH", "reuse_recorded_overlap", "element-000003",
        "700", "100", "The callout explains the next-payout field.",
    ])
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    START_INTAKE.gap_resolution.run(
        attempt,
        **inputs,
        purpose=REAL_PURPOSE,
        input_fn=answer,
        output_fn=lambda _message: None,
    )
    candidate = json.loads((attempt / "verification-candidate.json").read_text())

    assert candidate["relationships"][0]["to_id"] == "element-000003"
    assert len(candidate["elements"]) == 3
    assert not any(item["id"].startswith("resolution-element-") for item in candidate["elements"])
    overlap_prompt = next(
        prompt for prompt in prompts if "spatially overlapping recorded element" in prompt
    )
    assert "element-000003" in overlap_prompt
    assert "May 16 · ACH" in overlap_prompt
