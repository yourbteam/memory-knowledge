from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


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
PDF_PROJECTION_SCRIPT = (
    ROOT / "skills" / "info-intake-machinery" / "scripts" / "pdf_projection.py"
)
PDF_PROJECTION_SPEC = importlib.util.spec_from_file_location(
    "pdf_projection", PDF_PROJECTION_SCRIPT
)
assert PDF_PROJECTION_SPEC and PDF_PROJECTION_SPEC.loader
PDF_PROJECTION = importlib.util.module_from_spec(PDF_PROJECTION_SPEC)
PDF_PROJECTION_SPEC.loader.exec_module(PDF_PROJECTION)


def _visible_pdf(*page_texts: str) -> bytes:
    """Build a small dependency-free PDF whose pages have distinct visible text."""
    if not page_texts:
        raise ValueError("at least one PDF page is required")
    objects: list[bytes] = [b""]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{4 + (2 * index)} 0 R" for index in range(len(page_texts)))
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_texts)} >>".encode()
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, text in enumerate(page_texts):
        page_object = 4 + (2 * index)
        content_object = page_object + 1
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 18 Tf 72 720 Td ({escaped}) Tj ET\n".encode()
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                "/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_object} 0 R >>"
            ).encode()
        )
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode()
            + stream
            + b"endstream"
        )
    content = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, value in enumerate(objects[1:], start=1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode())
        content.extend(value)
        content.extend(b"\nendobj\n")
    xref = len(content)
    content.extend(f"xref\n0 {len(objects)}\n".encode())
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        (
            f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    return bytes(content)


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


def test_codex_projection_runner_accepts_follow_up_question_round(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    source = work / "sources" / "source-000003"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"image")
    (work / "intake-state.json").write_text(json.dumps({
        "status": "waiting_for_model",
        "phase": "formulating_follow_up_gap_question_round",
        "waiting_for": "gap-question-rounds/round-000003/interview.jsonl",
        "follow_up_gap_question_round": {"round": 3},
        "first_source": {
            "stored_path": "sources/source-000003",
            "media_type": "image/png",
            "sha256": START_INTAKE._digest_bytes(source.read_bytes()),
        },
    }))

    attachment, command = CODEX_RUNNER.load_request(work)

    assert attachment == source
    assert command[-1] == "--run-gap-clarification"


def test_codex_runner_accepts_prepared_answer_assessment_round(tmp_path: Path) -> None:
    source = tmp_path / "sources" / "source-000003"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"image")
    (tmp_path / "intake-state.json").write_text(json.dumps({
        "status": "waiting_for_model",
        "phase": "assessing_prepared_question_round_answers",
        "waiting_for": "gap-answer-assessments/round-000004/interview.jsonl",
        "prepared_question_round_interview": {"round": 4},
        "first_source": {
            "stored_path": "sources/source-000003",
            "media_type": "image/png",
            "sha256": START_INTAKE._digest_bytes(source.read_bytes()),
        },
    }))

    attachment, command = CODEX_RUNNER.load_request(tmp_path)

    assert attachment == source
    assert command[-1] == "--run-gap-answer-assessment"


def test_codex_runner_crosses_human_boundary_and_continues_to_completion(
    tmp_path: Path, monkeypatch: object, capsys: object,
) -> None:
    work = tmp_path / "intake"
    attachment = work / "sources" / "source-000003"
    first_command = ["python", "start_intake.py", "--run-gap-clarification"]
    second_command = ["python", "start_intake.py", "--run-gap-answer-assessment"]
    requests = iter([
        (attachment, first_command),
        (attachment, second_command),
    ])
    boundaries = iter([
        {
            "boundary": "needs_operator_answer",
            "status": "needs_operator",
            "question": {"id": "question-1", "asks": "Which element?"},
        },
        {
            "boundary": "needs_model_interview",
            "status": "waiting_for_model",
            "work": [{
                "attachments": [str(attachment)],
                "command": second_command,
            }],
        },
        {
            "boundary": "clarification_complete",
            "status": "ready_for_projection_assessment",
            "stopped": "clarification_continuation_complete",
        },
    ])
    model_calls: list[list[str]] = []
    operator_calls: list[Path] = []
    state_hashes = iter(["a" * 64, "a" * 64])

    monkeypatch.setattr("builtins.input", lambda _prompt: str(work))
    monkeypatch.setattr(CODEX_RUNNER.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(CODEX_RUNNER, "load_request", lambda _work: next(requests))
    monkeypatch.setattr(CODEX_RUNNER, "_sha256", lambda _path: next(state_hashes))
    monkeypatch.setattr(
        CODEX_RUNNER,
        "build_codex_argv",
        lambda _executable, _work, _attachment, command: command,
    )
    monkeypatch.setattr(
        CODEX_RUNNER,
        "run_clarification_boundary",
        lambda _work: next(boundaries),
    )
    monkeypatch.setattr(
        CODEX_RUNNER,
        "conduct_operator_turn",
        lambda selected_work: operator_calls.append(selected_work) or 0,
    )

    def run_model(argv: list[str], **_kwargs: object) -> object:
        model_calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(CODEX_RUNNER.subprocess, "run", run_model)
    monkeypatch.setattr(CODEX_RUNNER.sys, "argv", [str(CODEX_RUNNER_SCRIPT)])

    assert CODEX_RUNNER.main() == 0
    output = capsys.readouterr().out
    assert model_calls == [first_command, second_command]
    assert operator_calls == [work]
    assert '"boundary": "clarification_complete"' in output


def test_codex_runner_rejects_an_identical_repeated_model_stage(
    tmp_path: Path, monkeypatch: object, capsys: object,
) -> None:
    work = tmp_path / "intake"
    attachment = work / "sources" / "source-000003"
    command = ["python", "start_intake.py", "--run-gap-clarification"]
    requests = iter([(attachment, command), (attachment, command)])
    boundary = {
        "boundary": "needs_model_interview",
        "status": "waiting_for_model",
        "work": [{
            "attachments": [str(attachment)],
            "command": command,
        }],
    }
    model_calls: list[list[str]] = []

    monkeypatch.setattr("builtins.input", lambda _prompt: str(work))
    monkeypatch.setattr(CODEX_RUNNER.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(CODEX_RUNNER, "load_request", lambda _work: next(requests))
    monkeypatch.setattr(CODEX_RUNNER, "_sha256", lambda _path: "a" * 64)
    monkeypatch.setattr(
        CODEX_RUNNER,
        "build_codex_argv",
        lambda _executable, _work, _attachment, selected: selected,
    )
    monkeypatch.setattr(
        CODEX_RUNNER,
        "run_clarification_boundary",
        lambda _work: boundary,
    )

    def run_model(argv: list[str], **_kwargs: object) -> object:
        model_calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(CODEX_RUNNER.subprocess, "run", run_model)
    monkeypatch.setattr(CODEX_RUNNER.sys, "argv", [str(CODEX_RUNNER_SCRIPT)])

    assert CODEX_RUNNER.main() == 3
    output = capsys.readouterr().out
    assert model_calls == [command]
    assert "the intake did not advance after a model stage" in output


def test_operator_turn_presents_revalidates_and_submits_exact_answer(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    (work / "sources").mkdir(parents=True)
    (work / "sources" / "source-000001.txt").write_text("There is a new intake")
    (work / "sources" / "source-000002.txt").write_text(REAL_PURPOSE)
    boundary = {
        "boundary": "needs_operator_answer",
        "status": "needs_operator",
        "round": 2,
        "answered_question_count": 0,
        "question": {"id": "question-1", "asks": "Which exact element?"},
    }
    drive_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    messages: list[str] = []
    accepted = {"status": "ready_for_projection_assessment"}

    monkeypatch.setattr(
        START_INTAKE,
        "run_clarification_boundary",
        lambda _work: boundary,
    )

    def drive_answer(*args: object, **kwargs: object) -> dict[str, object]:
        drive_calls.append((args, kwargs))
        return accepted

    monkeypatch.setattr(START_INTAKE, "drive", drive_answer)
    result = START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda prompt: "The $48,000 Projected Close value",
        output_fn=messages.append,
    )

    assert result == accepted
    assert messages == [
        "Question: Which exact element?",
        "Answer type: non-empty text",
    ]
    assert drive_calls == [((work, "There is a new intake", REAL_PURPOSE), {
        "gap_answer": "The $48,000 Projected Close value",
    })]


def test_operator_turn_routes_a_file_typed_question_only_as_a_local_file(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    additional = tmp_path / "reference.png"
    additional.write_bytes(b"reference")
    (work / "sources").mkdir(parents=True)
    (work / "sources" / "source-000001.txt").write_text("There is a new intake")
    (work / "sources" / "source-000002.txt").write_text(REAL_PURPOSE)
    boundary = {
        "boundary": "needs_operator_answer",
        "status": "needs_operator",
        "round": 1,
        "answered_question_count": 0,
        "question": {
            "id": "question-1",
            "asks": "Which additional file contains the missing evidence?",
            "answer_type": "local_file",
        },
    }
    drive_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    messages: list[str] = []
    monkeypatch.setattr(
        START_INTAKE, "run_clarification_boundary", lambda _work: boundary
    )

    def drive_file(*args: object, **kwargs: object) -> dict[str, object]:
        drive_calls.append((args, kwargs))
        return {"status": "ready_for_projection"}

    monkeypatch.setattr(START_INTAKE, "drive", drive_file)
    result = START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda _prompt: str(additional),
        output_fn=messages.append,
    )

    assert result == {"status": "ready_for_projection"}
    assert messages == [
        "Question: Which additional file contains the missing evidence?",
        "Answer type: one existing local file path",
    ]
    assert drive_calls == [((work, "There is a new intake", REAL_PURPOSE), {
        "gap_file": additional,
    })]


def test_codex_runner_rejects_model_boundary_command_drift(
    tmp_path: Path, monkeypatch: object,
) -> None:
    attachment = tmp_path / "source.png"
    command = ["python", "start_intake.py", "--run-gap-clarification"]
    monkeypatch.setattr(
        CODEX_RUNNER,
        "load_request",
        lambda _work: (attachment, command),
    )
    result = {
        "boundary": "needs_model_interview",
        "status": "waiting_for_model",
        "work": [{
            "attachments": [str(attachment)],
            "command": ["python", "uncontrolled.py"],
        }],
    }

    try:
        CODEX_RUNNER.next_model_request(tmp_path, result)
    except CODEX_RUNNER.LaunchError as error:
        assert str(error) == "the model boundary command does not match the saved intake"
    else:
        raise AssertionError("a drifted model command was accepted")


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


class _URLResponse:
    def __init__(
        self,
        status: int,
        headers: list[tuple[str, str]],
        body: bytes = b"",
        reason: str = "OK",
    ) -> None:
        self.status = status
        self.reason = reason
        self._headers = headers
        self._body = body
        self._offset = 0

    def getheaders(self) -> list[tuple[str, str]]:
        return self._headers

    def read(self, size: int) -> bytes:
        result = self._body[self._offset : self._offset + size]
        self._offset += len(result)
        return result


class _URLConnection:
    def __init__(self, response: _URLResponse) -> None:
        self.response = response
        self.requested: tuple[str, str, dict[str, str]] | None = None
        self.closed = False

    def request(
        self, method: str, target: str, *, headers: dict[str, str]
    ) -> None:
        self.requested = (method, target, headers)

    def getresponse(self) -> _URLResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_public_url_fetch_preserves_redirect_and_exact_response_bytes(
    monkeypatch: object,
) -> None:
    responses = iter([
        _URLResponse(
            302,
            [("Location", "https://cdn.example.test/final.txt#section"), ("X-Hop", "one")],
            reason="Found",
        ),
        _URLResponse(
            200,
            [("Content-Type", "text/plain; charset=utf-8"), ("X-Final", "yes")],
            "exact π\n".encode("utf-8"),
        ),
    ])
    connections: list[_URLConnection] = []
    monkeypatch.setattr(
        START_INTAKE.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (START_INTAKE.socket.AF_INET, START_INTAKE.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )

    def connect(*_args: object) -> _URLConnection:
        connection = _URLConnection(next(responses))
        connections.append(connection)
        return connection

    monkeypatch.setattr(START_INTAKE, "_url_connection", connect)

    retrieval, content, error = START_INTAKE._fetch_public_url(
        "https://example.test/start#operator-note"
    )

    assert error is None
    assert content == "exact π\n".encode("utf-8")
    assert retrieval["provided_url"] == "https://example.test/start#operator-note"
    assert retrieval["request_url"] == "https://example.test/start"
    assert retrieval["final_url"] == "https://cdn.example.test/final.txt"
    assert retrieval["redirect_chain"][0]["next_url"] == (
        "https://cdn.example.test/final.txt"
    )
    assert retrieval["response"]["headers"][-1] == {
        "name": "X-Final",
        "value": "yes",
    }
    assert connections[0].requested[0:2] == ("GET", "/start")
    assert connections[1].requested[0:2] == ("GET", "/final.txt")
    assert all(connection.closed for connection in connections)


def test_public_url_fetch_rejects_unsafe_redirect_without_second_request(
    monkeypatch: object,
) -> None:
    requested: list[str] = []

    def resolve(host: str, *_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
        address = "127.0.0.1" if host == "127.0.0.1" else "93.184.216.34"
        return [(START_INTAKE.socket.AF_INET, START_INTAKE.socket.SOCK_STREAM, 6, "", (address, 443))]

    monkeypatch.setattr(START_INTAKE.socket, "getaddrinfo", resolve)

    def connect(_scheme: str, _host: str, address: str, _port: int) -> _URLConnection:
        requested.append(address)
        return _URLConnection(
            _URLResponse(302, [("Location", "http://127.0.0.1/private")], reason="Found")
        )

    monkeypatch.setattr(START_INTAKE, "_url_connection", connect)

    retrieval, content, error = START_INTAKE._fetch_public_url(
        "https://example.test/start"
    )

    assert retrieval is None and content is None
    assert error["stopped"] == "unsafe URL destination"
    assert requested == ["93.184.216.34"]


def test_public_url_fetch_rejects_credentials_scheme_and_oversized_response(
    monkeypatch: object,
) -> None:
    for url, stopped in (
        ("file:///tmp/source", "URL scheme unsupported"),
        ("https://operator:secret@example.test/source", "URL credentials prohibited"),
    ):
        retrieval, content, error = START_INTAKE._fetch_public_url(url)
        assert retrieval is None and content is None
        assert error["stopped"] == stopped

    monkeypatch.setattr(
        START_INTAKE.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (START_INTAKE.socket.AF_INET, START_INTAKE.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    unsuccessful = _URLConnection(
        _URLResponse(404, [("Content-Type", "text/plain")], reason="Not Found")
    )
    monkeypatch.setattr(
        START_INTAKE, "_url_connection", lambda *_args: unsuccessful
    )
    retrieval, content, error = START_INTAKE._fetch_public_url(
        "https://example.test/missing"
    )
    assert retrieval is None and content is None
    assert error["stopped"] == "URL response unsuccessful"
    assert unsuccessful.closed is True

    connection = _URLConnection(
        _URLResponse(
            200,
            [("Content-Length", str(START_INTAKE.URL_MAX_BYTES + 1))],
        )
    )
    monkeypatch.setattr(
        START_INTAKE, "_url_connection", lambda *_args: connection
    )

    retrieval, content, error = START_INTAKE._fetch_public_url(
        "https://example.test/large"
    )

    assert retrieval is None and content is None
    assert error["stopped"] == "URL response too large"
    assert connection.closed is True


def test_public_url_fetch_reports_resolution_timeout_and_redirect_limit(
    monkeypatch: object,
) -> None:
    def resolution_failure(*_args: object, **_kwargs: object) -> object:
        raise START_INTAKE.socket.gaierror("no address")

    monkeypatch.setattr(
        START_INTAKE.socket, "getaddrinfo", resolution_failure
    )
    retrieval, content, error = START_INTAKE._fetch_public_url(
        "https://example.test/source"
    )
    assert retrieval is None and content is None
    assert error["stopped"] == "URL resolution failed"

    monkeypatch.setattr(
        START_INTAKE.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (START_INTAKE.socket.AF_INET, START_INTAKE.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )

    def timeout(*_args: object) -> object:
        raise TimeoutError("timed out")

    monkeypatch.setattr(START_INTAKE, "_url_connection", timeout)
    retrieval, content, error = START_INTAKE._fetch_public_url(
        "https://example.test/source"
    )
    assert retrieval is None and content is None
    assert error["stopped"] == "URL retrieval failed"
    assert "timed out" in error["why"]

    connections: list[_URLConnection] = []

    def redirect(*_args: object) -> _URLConnection:
        connection = _URLConnection(
            _URLResponse(302, [("Location", "/again")], reason="Found")
        )
        connections.append(connection)
        return connection

    monkeypatch.setattr(START_INTAKE, "_url_connection", redirect)
    retrieval, content, error = START_INTAKE._fetch_public_url(
        "https://example.test/start"
    )
    assert retrieval is None and content is None
    assert error["stopped"] == "URL redirect limit exceeded"
    assert len(connections) == START_INTAKE.URL_MAX_REDIRECTS + 1
    assert all(connection.closed for connection in connections)


def test_first_public_url_is_frozen_once_then_projected_verbatim(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    content = "public source π\n".encode("utf-8")
    connection = _URLConnection(
        _URLResponse(200, [("Content-Type", "text/plain; charset=utf-8")], content)
    )
    monkeypatch.setattr(
        START_INTAKE.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (START_INTAKE.socket.AF_INET, START_INTAKE.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    monkeypatch.setattr(
        START_INTAKE, "_url_connection", lambda *_args: connection
    )
    _advance_to_first_source(work)

    frozen = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_url="https://example.test/source.txt#note",
    )
    ledger_after_freeze = (work / "ledger.jsonl").read_bytes()
    monkeypatch.setattr(
        START_INTAKE,
        "_fetch_public_url",
        lambda *_args: (_ for _ in ()).throw(AssertionError("URL was fetched again")),
    )
    replay = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_url="https://example.test/source.txt#note",
    )
    projected = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )

    assert frozen == replay
    assert frozen["source"]["kind"] == "url"
    assert frozen["source"]["adapter"] == {"name": "url", "version": 1}
    assert frozen["source"]["provided_url"] == "https://example.test/source.txt#note"
    assert frozen["source"]["request_url"] == "https://example.test/source.txt"
    assert frozen["source"]["response"]["connected_address"] == "93.184.216.34"
    assert (work / frozen["source"]["stored_path"]).read_bytes() == content
    assert (work / projected["projection"]["path"]).read_bytes() == content
    assert projected["projection"]["method"] == "verbatim_utf8"
    assert START_INTAKE.run_source_projection_closure(work)["verdict"] == "all_projected"
    assert len((work / "ledger.jsonl").read_bytes().splitlines()) == (
        len(ledger_after_freeze.splitlines()) + 1
    )


def test_unsafe_first_url_does_not_create_source_or_advance_ledger(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    _advance_to_first_source(work)
    before = (work / "ledger.jsonl").read_bytes()
    monkeypatch.setattr(
        START_INTAKE.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (START_INTAKE.socket.AF_INET, START_INTAKE.socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))
        ],
    )

    result = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_url="http://localhost/private",
    )

    assert result["status"] == "blocked"
    assert result["stopped"] == "unsafe URL destination"
    assert not (work / "sources" / "source-000003").exists()
    assert (work / "ledger.jsonl").read_bytes() == before


def test_unbound_first_url_artifact_blocks_before_network_access(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    _advance_to_first_source(work)
    unbound = work / "sources" / "source-000003"
    unbound.write_bytes(b"unbound")
    before = (work / "ledger.jsonl").read_bytes()
    monkeypatch.setattr(
        START_INTAKE,
        "_fetch_public_url",
        lambda *_args: (_ for _ in ()).throw(AssertionError("network was accessed")),
    )

    result = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_url="https://example.test/source",
    )

    assert result["status"] == "blocked"
    assert result["stopped"] == "unbound source artifact"
    assert unbound.read_bytes() == b"unbound"
    assert (work / "ledger.jsonl").read_bytes() == before


def test_cli_routes_source_url_through_the_url_adapter(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_first_source(work)
    before = (work / "ledger.jsonl").read_bytes()
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--work",
            str(work),
            "--opening",
            "There is a new intake",
            "--purpose",
            REAL_PURPOSE,
            "--source-url",
            "file:///tmp/not-public",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 3
    assert json.loads(completed.stdout)["stopped"] == "URL scheme unsupported"
    assert (work / "ledger.jsonl").read_bytes() == before


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


def test_two_page_pdf_projects_every_visible_page_in_fixed_order(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "two-pages.pdf"
    supplied.write_bytes(_visible_pdf("Page one description", "Page two note"))
    _advance_to_first_source(work)
    frozen = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, supplied
    )

    current = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    assert frozen["source"]["media_type"] == "application/pdf"
    assert current["pdf_page"] == 1
    assert CODEX_RUNNER.load_request(work)[0].name == "page-000001.png"

    for page_number, visible_text in enumerate(
        ("Page one description", "Page two note"), start=1
    ):
        answers = _projection_answers(contract=7)
        answers[answers.index("A readable description")] = visible_text
        answer_iterator = iter(answers)
        verifying = START_INTAKE.run_first_projection_interview(
            work,
            input_fn=lambda _prompt: next(answer_iterator),
            output_fn=lambda _message: None,
        )
        assert verifying["stopped"] == "verifying_first_projection", verifying
        verification_iterator = iter(_verification_answers(1))
        current = START_INTAKE.run_first_projection_verification(
            work,
            input_fn=lambda _prompt: next(verification_iterator),
            output_fn=lambda _message: None,
        )
        if page_number == 1:
            assert current["pdf_page"] == 2
            assert CODEX_RUNNER.load_request(work)[0].name == "page-000002.png"
            pending = START_INTAKE.run_source_projection_closure(work)
            assert pending["verdict"] == "conversion_incomplete"
            assert pending["outcomes"][-1]["outcome"] == "pending"
            assert "completed 1 of 2 pages" in pending["outcomes"][-1]["reason"]

    replay = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    manifest = json.loads((work / current["projection"]["path"]).read_text())
    page_contents = [
        json.loads((work / item["readable_projection"]["path"]).read_text())[
            "elements"
        ][0]["content"]
        for item in manifest["pages"]
    ]
    ledger = [json.loads(line) for line in (work / "ledger.jsonl").read_text().splitlines()]

    assert current == replay
    assert current["stopped"] == "first_pdf_projection_recorded"
    assert current["projection"]["method"] == "pdf_visible_pages"
    assert current["projection"]["coverage"]["status"] == "complete"
    assert current["projection"]["coverage"]["gaps"] == [
        "page 1: 1 explicit projection gaps",
        "page 2: 1 explicit projection gaps",
    ]
    assert [item["page"] for item in manifest["pages"]] == [1, 2]
    assert [item["page"] for item in manifest["gap_inventory"]] == [1, 2]
    assert [item["item_id"] for item in manifest["gap_inventory"]] == [
        "element-000002",
        "element-000002",
    ]
    assert page_contents == ["Page one description", "Page two note"]
    assert [entry["event"] for entry in ledger[-4:]] == [
        "pdf_projection_started",
        "pdf_page_projection_completed",
        "pdf_page_projection_completed",
        "projection_version_created",
    ]
    assert START_INTAKE.run_source_projection_closure(work)["verdict"] == "all_projected"
    boundary = START_INTAKE.run_clarification_boundary(work)
    assert boundary["boundary"] == "needs_model_interview"
    assert boundary["stopped"] == "formulating_gap_question_round"
    assert [Path(path).name for path in boundary["work"][0]["attachments"]] == [
        "page-000001.png",
        "page-000002.png",
    ]
    state = json.loads((work / "intake-state.json").read_text())
    assert [item["page"] for item in state["gap_question_round"]["gaps"]] == [1, 2]
    assert [item["item_id"] for item in state["gap_question_round"]["gaps"]] == [
        "element-000002",
        "element-000002",
    ]
    assert state["gap_question_round"]["request_ledger_sequence"] == 12
    attachments, command = CODEX_RUNNER.load_request(work)
    assert CODEX_RUNNER.next_model_request(work, boundary) == (
        attachments,
        command,
    )
    assert isinstance(attachments, tuple)
    assert [path.name for path in attachments] == [
        "page-000001.png",
        "page-000002.png",
    ]
    argv = CODEX_RUNNER.build_codex_argv(
        "/usr/local/bin/codex", work, attachments, command
    )
    assert [argv[index + 1] for index, value in enumerate(argv) if value == "--image"] == [
        str(attachments[0]),
        str(attachments[1]),
    ]
    answers = iter([
        "fresh-questioner",
        "pytest-gap-question",
        "operator_text",
        "What exact value is unreadable in the identified element on page one?",
        "operator_text",
        "What exact value is unreadable in the identified element on page two?",
    ])
    waiting = START_INTAKE.run_gap_clarification(
        work,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    assert waiting["stopped"] == "awaiting_gap_answers"
    assert waiting["question_count"] == 2
    assert waiting["answered_question_count"] == 0
    assert waiting["question"]["answers_gap"]["page"] == 1
    assert waiting["question"]["answers_gap"]["item_id"] == "element-000002"
    assert "questions" not in waiting
    state_path = work / "intake-state.json"
    changed = json.loads(state_path.read_text())
    changed["gap_question_round"]["gaps"][0]["page"] = 2
    state_path.write_text(json.dumps(changed))
    refused = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    assert refused["status"] == "blocked"
    assert refused["stopped"] == "invalid ledger"


def test_pdf_render_change_fails_replay_before_model_intake(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "source.pdf"
    supplied.write_bytes(_visible_pdf("Visible page"))
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    rendered = (
        work
        / "pdf-projections/source-000003-v1/rendered-pages/page-000001.png"
    )
    rendered.write_bytes(b"changed")

    result = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)

    assert result["status"] == "blocked"
    assert result["stopped"] == "immutable PDF rendering changed"


def test_malformed_pdf_preserves_one_terminal_conversion_failure(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "malformed.pdf"
    supplied.write_bytes(b"%PDF-1.7\nmalformed\n")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)

    failed = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    ledger_before = (work / "ledger.jsonl").read_bytes()
    replay = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    closure = START_INTAKE.run_source_projection_closure(work)

    assert failed == replay
    assert failed["stopped"] == "first_pdf_projection_failed"
    assert failed["projection"]["status"] == "failed"
    assert failed["projection"]["path"] is None
    assert (work / "ledger.jsonl").read_bytes() == ledger_before
    assert closure["verdict"] == "conversion_incomplete"
    assert closure["outcomes"][-1]["outcome"] == "failed"
    assert closure["outcomes"][-1]["projection"]["status"] == "failed"


def test_pdf_adapter_rejects_unsupported_features_and_bounds(
    tmp_path: Path, monkeypatch: object,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(_visible_pdf("Visible page"))
    for fields, message in (
        ({"Encrypted": "yes", "Form": "none", "JavaScript": "no"}, "encrypted"),
        ({"Encrypted": "no", "Form": "AcroForm", "JavaScript": "no"}, "forms"),
        ({"Encrypted": "no", "Form": "none", "JavaScript": "yes"}, "JavaScript"),
    ):
        with pytest.raises(PDF_PROJECTION.PDFProjectionError, match=message):
            PDF_PROJECTION._reject_unsupported_features(source, fields)
    monkeypatch.setattr(
        PDF_PROJECTION,
        "_run",
        lambda command: subprocess.CompletedProcess(
            command, 0, "1 embedded file\n", ""
        ),
    )
    with pytest.raises(PDF_PROJECTION.PDFProjectionError, match="attachments"):
        PDF_PROJECTION._reject_unsupported_features(
            source, {"Encrypted": "no", "Form": "none", "JavaScript": "no"}
        )
    with pytest.raises(PDF_PROJECTION.PDFProjectionError, match="no visible pages"):
        PDF_PROJECTION._page_count({"Pages": "0"})
    with pytest.raises(PDF_PROJECTION.PDFProjectionError, match="limit"):
        PDF_PROJECTION._page_count({"Pages": str(PDF_PROJECTION.MAX_PAGES + 1)})


def test_pdf_adapter_fails_cleanly_on_renderer_error_and_changed_output(
    tmp_path: Path, monkeypatch: object,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(_visible_pdf("Visible page"))
    source_sha256 = PDF_PROJECTION._sha256(source)
    output = tmp_path / "failed" / "pdf-projections/source-000003-v1"
    original_run = PDF_PROJECTION._run

    def fail_renderer(command: list[str]) -> subprocess.CompletedProcess[str]:
        if Path(command[0]).name == "pdftoppm" and "-singlefile" in command:
            return subprocess.CompletedProcess(command, 1, "", "render failed")
        return original_run(command)

    monkeypatch.setattr(PDF_PROJECTION, "_run", fail_renderer)
    with pytest.raises(PDF_PROJECTION.PDFProjectionError, match="rendering failed"):
        PDF_PROJECTION.prepare(
            source,
            output,
            source_id="source-000003",
            source_sha256=source_sha256,
        )
    assert not output.exists()

    monkeypatch.setattr(PDF_PROJECTION, "_run", original_run)
    valid_output = tmp_path / "valid" / "pdf-projections/source-000003-v1"
    prepared = PDF_PROJECTION.prepare(
        source,
        valid_output,
        source_id="source-000003",
        source_sha256=source_sha256,
    )
    rendered = valid_output / "rendered-pages/page-000001.png"
    rendered.write_bytes(b"changed")
    with pytest.raises(PDF_PROJECTION.PDFProjectionError, match="valid PNG"):
        PDF_PROJECTION.validate_prepared(tmp_path / "valid", prepared)
    with pytest.raises(PDF_PROJECTION.PDFProjectionError, match="unbound"):
        PDF_PROJECTION.prepare(
            source,
            valid_output,
            source_id="source-000003",
            source_sha256=source_sha256,
        )


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


def test_first_utf8_file_is_projected_verbatim_without_model_work(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "first.txt"
    supplied_bytes = "plain text\nπ\n".encode("utf-8")
    supplied.write_bytes(supplied_bytes)
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    before = (work / "ledger.jsonl").read_bytes()

    result = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    after = (work / "ledger.jsonl").read_bytes()

    assert result["status"] == "ready_for_projection_assessment"
    assert result["stopped"] == "first_verbatim_projection_recorded"
    assert result["projection"]["method"] == "verbatim_utf8"
    assert result["projection"]["coverage"]["status"] == "complete"
    assert (work / result["projection"]["path"]).read_bytes() == supplied_bytes
    assert len(after.decode("utf-8").splitlines()) == len(
        before.decode("utf-8").splitlines()
    ) + 1
    assert START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE) == result
    boundary = START_INTAKE.run_clarification_boundary(work)
    assert boundary["boundary"] == "first_source_projection_complete"
    assert boundary["projection"] == result["projection"]
    closure = START_INTAKE.run_source_projection_closure(work)
    assert closure["verdict"] == "all_projected"
    assert closure["outcome_counts"] == {
        "projected": 3,
        "pending": 0,
        "failed": 0,
    }
    assert (work / "ledger.jsonl").read_bytes() == after


def test_invalid_utf8_file_fails_without_filling_its_reservation(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "binary.dat"
    supplied.write_bytes(b"readable-prefix\xff\xfe")
    _advance_to_first_source(work)
    frozen = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, supplied
    )
    before = (work / "ledger.jsonl").read_bytes()

    result = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )

    assert result["status"] == "blocked"
    assert result["stopped"] == "projection adapter unavailable"
    assert "not valid UTF-8" in result["why"]
    assert not (work / "projections" / "source-000003-v1.txt").exists()
    assert (work / "ledger.jsonl").read_bytes() == before
    assert frozen["stopped"] == "first_source_frozen"
    closure = START_INTAKE.run_source_projection_closure(work)
    assert closure["verdict"] == "conversion_incomplete"
    assert closure["outcome_counts"] == {
        "projected": 2,
        "pending": 0,
        "failed": 1,
    }
    assert closure["outcomes"][-1]["outcome"] == "failed"
    assert "not valid UTF-8" in closure["outcomes"][-1]["reason"]


def test_verbatim_projection_rejects_a_preexisting_unbound_artifact(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "first.md"
    supplied.write_text("# Existing repository notes\n")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    projection_path = work / "projections" / "source-000003-v1.txt"
    projection_path.write_text("unbound content\n")
    before = (work / "ledger.jsonl").read_bytes()

    result = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )

    assert result["status"] == "blocked"
    assert result["stopped"] == "unbound projection artifact"
    assert projection_path.read_text() == "unbound content\n"
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

    requested = START_INTAKE.run_clarification_boundary(work)
    ledger_at_model_boundary = (work / "ledger.jsonl").read_bytes()
    repeated_model_boundary = START_INTAKE.run_clarification_boundary(work)
    assert repeated_model_boundary == requested
    assert (work / "ledger.jsonl").read_bytes() == ledger_at_model_boundary
    attachment, command = CODEX_RUNNER.load_request(work)
    argv = CODEX_RUNNER.build_codex_argv(
        "/usr/local/bin/codex", work, attachment, command,
    )
    question_answers = iter([
        "fresh-questioner",
        "pytest-gap-question",
        "operator_text",
        "What exact information is hidden by the first obscured target?",
        "operator_text",
        "What exact information is hidden by the second obscured target?",
    ])
    waiting = START_INTAKE.run_gap_clarification(
        work,
        input_fn=lambda _prompt: next(question_answers),
        output_fn=lambda _message: None,
    )

    assert requested["stopped"] == "formulating_gap_question_round"
    assert requested["boundary"] == "needs_model_interview"
    assert command[-1] == "--run-gap-clarification"
    assert argv[argv.index("--image") + 1] == str(work / "sources" / "source-000003")
    assert "each code-bound gap" in argv[-1]
    assert waiting["status"] == "needs_operator"
    assert waiting["stopped"] == "awaiting_gap_answers"
    assert waiting["answered_question_count"] == 0
    assert waiting["question_count"] == 2
    assert waiting["question"]["answers_gap"]["id"] == "element-000002"
    assert "questions" not in waiting
    ledger_before_operator_boundary = (work / "ledger.jsonl").read_bytes()
    operator_boundary = START_INTAKE.run_clarification_boundary(work)
    assert operator_boundary["boundary"] == "needs_operator_answer"
    assert operator_boundary["question"] == waiting["question"]
    assert (work / "ledger.jsonl").read_bytes() == ledger_before_operator_boundary
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

    assessment_requested = START_INTAKE.run_clarification_boundary(work)
    assessment_attachment, assessment_command = CODEX_RUNNER.load_request(work)
    assessment_argv = CODEX_RUNNER.build_codex_argv(
        "/usr/local/bin/codex", work, assessment_attachment, assessment_command,
    )
    assessment_answers = iter([
        "fresh-assessor",
        "pytest-gap-answer-assessment",
        "maybe",
        "does_not_resolve_gap",
        "The first answer gives a value without identifying visible evidence.",
        "does_not_resolve_gap",
        "The second answer repeats a value but does not identify the obscured target.",
    ])
    assessed = START_INTAKE.run_gap_answer_assessment(
        work,
        input_fn=lambda _prompt: next(assessment_answers),
        output_fn=lambda _message: None,
    )
    ledger_after_assessment = (work / "ledger.jsonl").read_bytes()
    state_after_assessment = (work / "intake-state.json").read_bytes()
    resumed_assessment = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE,
    )

    assert assessment_requested["status"] == "waiting_for_model"
    assert assessment_requested["stopped"] == "assessing_gap_answers"
    assert assessment_requested["boundary"] == "needs_model_interview"
    assert assessment_command[-1] == "--run-gap-answer-assessment"
    assert assessment_argv[assessment_argv.index("--image") + 1] == str(
        work / "sources" / "source-000003"
    )
    assert "each code-bound preserved answer" in assessment_argv[-1]
    assert assessed == resumed_assessment
    assert assessed["status"] == "ready_for_projection_assessment"
    assert assessed["stopped"] == "gap_answer_assessment_recorded"
    assert assessed["continuation"]["decision"] == "prepare_next_round"
    assert assessed["continuation"]["assessment_round"] == 1
    assert assessed["continuation"]["next_round"] == 2
    assert [item["id"] for item in assessed["continuation"]["gaps"]] == [
        "element-000002", "element-000003",
    ]
    assert (work / "ledger.jsonl").read_bytes() == ledger_after_assessment
    assert (work / "intake-state.json").read_bytes() == state_after_assessment
    assert [item["verdict"] for item in assessed["assessments"]] == [
        "does_not_resolve_gap", "does_not_resolve_gap",
    ]
    assert [item["gap"]["id"] for item in assessed["assessments"]] == [
        "element-000002", "element-000003",
    ]
    assert original_projection.read_bytes() == original_projection_before
    ledger_before_reassessment = (work / "ledger.jsonl").read_bytes()
    reassessment = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        assess_gap_answers=True,
    )
    assert reassessment == {
        "status": "blocked",
        "stopped": "gap answer assessment already recorded",
        "why": "this completed question round already has its immutable assessment",
    }
    assert (work / "ledger.jsonl").read_bytes() == ledger_before_reassessment
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

    round_two_requested = START_INTAKE.run_clarification_boundary(work)
    assert round_two_requested["status"] == "waiting_for_model"
    assert round_two_requested["boundary"] == "needs_model_interview"
    assert round_two_requested["round"] == 2
    round_two_questions = iter([
        "fresh-round-two-questioner",
        "pytest-round-two",
        "operator_text",
        "Which visible label identifies the first hidden value?",
        "operator_text",
        "Which visible label identifies the second hidden value?",
    ])
    round_two_ready = START_INTAKE.run_gap_clarification(
        work,
        input_fn=lambda _prompt: next(round_two_questions),
        output_fn=lambda _message: None,
    )
    assert round_two_ready["status"] == "ready_for_operator_interview"
    assert round_two_ready["round"] == 2
    round_two_interview = START_INTAKE.run_clarification_boundary(work)
    assert round_two_interview["status"] == "needs_operator"
    assert round_two_interview["boundary"] == "needs_operator_answer"
    round_two_ledger_at_operator = (work / "ledger.jsonl").read_bytes()
    repeated_round_two_operator = START_INTAKE.run_clarification_boundary(work)
    assert repeated_round_two_operator == round_two_interview
    assert (work / "ledger.jsonl").read_bytes() == round_two_ledger_at_operator
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_answer="The first value appears below the orange label.",
    )
    round_two_answered = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_answer="The second value appears beside the green label.",
    )
    assert round_two_answered["stopped"] == "prepared_question_round_answered"
    round_two_assessment_requested = START_INTAKE.run_clarification_boundary(work)
    assert round_two_assessment_requested["boundary"] == "needs_model_interview"
    assert round_two_assessment_requested["round"] == 2
    round_two_assessment_answers = iter([
        "fresh-round-two-assessor",
        "pytest-round-two-assessment",
        "does_not_resolve_gap",
        "The label description still does not identify the exact value.",
        "does_not_resolve_gap",
        "The label description still does not identify the exact value.",
    ])
    round_two_assessed = START_INTAKE.run_gap_answer_assessment(
        work,
        input_fn=lambda _prompt: next(round_two_assessment_answers),
        output_fn=lambda _message: None,
    )
    assert round_two_assessed["stopped"] == (
        "prepared_question_round_assessment_recorded"
    )
    assert round_two_assessed["round"] == 2
    assert round_two_assessed["continuation"]["decision"] == "prepare_next_round"
    assert round_two_assessed["continuation"]["next_round"] == 3

    round_three_requested = START_INTAKE.run_clarification_boundary(work)
    assert round_three_requested["status"] == "waiting_for_model"
    assert round_three_requested["boundary"] == "needs_model_interview"
    assert round_three_requested["round"] == 3
    state = json.loads((work / "intake-state.json").read_text())
    assert state["follow_up_gap_question_round"]["prior_assessment_round"] == 2
    assert [item["round"] for item in state["prepared_question_round_history"]] == [2]
    round_three_questions = iter([
        "fresh-round-three-questioner",
        "pytest-round-three",
        "local_file",
        "What exact value is paired with the first visible label?",
        "operator_text",
        "What exact value is paired with the second visible label?",
    ])
    round_three_ready = START_INTAKE.run_gap_clarification(
        work,
        input_fn=lambda _prompt: next(round_three_questions),
        output_fn=lambda _message: None,
    )
    assert round_three_ready["status"] == "ready_for_operator_interview"
    assert round_three_ready["round"] == 3
    round_three_operator = START_INTAKE.run_clarification_boundary(work)
    assert round_three_operator["boundary"] == "needs_operator_answer"
    assert round_three_operator["round"] == 3
    round_three_file = tmp_path / "round-three-reference.png"
    round_three_file.write_bytes(b"round three reference")
    round_three_frozen = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_file=round_three_file,
    )
    assert round_three_frozen["stopped"] == "additional_source_frozen"
    assert round_three_frozen["lineage"]["question_round"] == 3
    round_three_state = json.loads((work / "intake-state.json").read_text())
    assert round_three_frozen["lineage"]["prepared_round_result_sha256"] == (
        round_three_state["follow_up_gap_question_round"]["result_sha256"]
    )
    assert original_projection.read_bytes() == original_projection_before


def test_file_typed_gap_question_freezes_one_bound_source_and_stops_before_projection(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    projection_answers = iter(_projection_answers(contract=7))
    START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(projection_answers),
        output_fn=lambda _message: None,
    )
    verification_answers = iter(_verification_answers(1))
    recorded = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verification_answers),
        output_fn=lambda _message: None,
    )
    original_projection_path = work / recorded["projection"]["path"]
    original_projection_bytes = original_projection_path.read_bytes()
    requested = START_INTAKE.run_clarification_boundary(work)
    assert requested["boundary"] == "needs_model_interview"

    messages: list[str] = []
    question_answers = iter([
        "fresh-questioner",
        "pytest-gap-question",
        "image",
        "local_file",
        "Which additional local file shows the exact hidden value?",
    ])
    waiting = START_INTAKE.run_gap_clarification(
        work,
        input_fn=lambda _prompt: next(question_answers),
        output_fn=messages.append,
    )
    assert waiting["question"]["answer_type"] == "local_file"
    assert messages == [
        "Invalid answer: operator_answer_type_000001: choose one of: operator_text, local_file, url."
    ]

    ledger_before_rejections = (work / "ledger.jsonl").read_bytes()
    wrong_type = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_answer="The value is $48,000.",
    )
    assert wrong_type["stopped"] == "operator input type mismatch"
    missing = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_file=tmp_path / "missing.png",
    )
    assert missing["stopped"] == "source unavailable"
    wrong_file_kind = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_file=tmp_path,
    )
    assert wrong_file_kind["stopped"] == "source is not a file"
    assert (work / "ledger.jsonl").read_bytes() == ledger_before_rejections

    additional = tmp_path / "clean-reference.png"
    additional_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII="
    )
    additional.write_bytes(additional_bytes)
    frozen = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_file=additional,
    )
    ledger_after_freeze = (work / "ledger.jsonl").read_bytes()
    frozen_copy = work / frozen["source"]["stored_path"]
    assert frozen["status"] == "ready_for_projection"
    assert frozen["stopped"] == "additional_source_frozen"
    assert frozen["source"]["answers_question"] == waiting["question"]["id"]
    assert frozen["source"]["answers_gap"] == waiting["question"]["answers_gap"]
    assert frozen["projection"] == START_INTAKE._pending_additional_projection_record(4)
    assert frozen_copy.read_bytes() == additional_bytes
    assert original_projection_path.read_bytes() == original_projection_bytes
    assert not (work / "projections" / "source-000004-v1.txt").exists()

    pending_closure = START_INTAKE.run_source_projection_closure(work)
    assert pending_closure["verdict"] == "conversion_incomplete"
    assert pending_closure["outcome_counts"] == {
        "projected": 3,
        "pending": 1,
        "failed": 0,
    }
    assert pending_closure["outcomes"][-1]["outcome"] == "pending"
    assert pending_closure["outcomes"][-1]["reserved_projection"] == frozen[
        "projection"
    ]
    assert (work / "ledger.jsonl").read_bytes() == ledger_after_freeze

    resumed = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    assert resumed == frozen
    assert (work / "ledger.jsonl").read_bytes() == ledger_after_freeze

    additional.write_bytes(b"changed after freeze")
    changed = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_file=additional,
    )
    assert changed["stopped"] == "source changed"
    assert frozen_copy.read_bytes() == additional_bytes
    assert (work / "ledger.jsonl").read_bytes() == ledger_after_freeze

    frozen_copy.write_bytes(b"changed frozen bytes")
    changed_frozen = START_INTAKE.run_clarification_boundary(work)
    assert changed_frozen["stopped"] == "invalid ledger"
    assert (work / "ledger.jsonl").read_bytes() == ledger_after_freeze
    frozen_copy.write_bytes(additional_bytes)

    additional.write_bytes(additional_bytes)
    boundary = START_INTAKE.run_clarification_boundary(work)
    runner_boundary = CODEX_RUNNER.run_clarification_boundary(work)
    assert boundary.get("boundary") == "needs_model_interview", boundary
    assert runner_boundary == boundary
    assert boundary["work"][0]["attachments"] == [str(frozen_copy.resolve())]
    assert boundary["work"][0]["command"][-1] == "--run-projection-interview"
    attachment, command = CODEX_RUNNER.load_request(work)
    assert attachment == frozen_copy
    assert command == boundary["work"][0]["command"]

    additional_projection_answers = iter(_projection_answers(contract=7))
    verifying = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(additional_projection_answers),
        output_fn=lambda _message: None,
    )
    assert verifying["stopped"] == "verifying_additional_source_projection"
    additional_verification_answers = iter(_verification_answers(1))
    projected = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(additional_verification_answers),
        output_fn=lambda _message: None,
    )
    completed_boundary = START_INTAKE.run_clarification_boundary(work)
    ledger_after_projection = (work / "ledger.jsonl").read_bytes()

    assert projected["stopped"] == "additional_source_projection_recorded"
    assert projected["projection"]["id"] == "projection-source-000004-v1"
    assert projected["projection"]["source_id"] == "source-000004"
    assert projected["projection"]["coverage"] == "unassessed"
    assert projected["reserved_projection"] == frozen["projection"]
    assert projected["lineage"] == frozen["lineage"]
    assert completed_boundary["boundary"] == "additional_source_projection_complete"
    assert completed_boundary["projection"] == projected["projection"]
    assert original_projection_path.read_bytes() == original_projection_bytes
    assert START_INTAKE.run_clarification_boundary(work) == completed_boundary
    assert (work / "ledger.jsonl").read_bytes() == ledger_after_projection

    before_closure = {
        path.relative_to(work): path.read_bytes()
        for path in work.rglob("*")
        if path.is_file()
    }
    closure = START_INTAKE.run_source_projection_closure(work)
    replayed_closure = START_INTAKE.run_source_projection_closure(work)
    after_closure = {
        path.relative_to(work): path.read_bytes()
        for path in work.rglob("*")
        if path.is_file()
    }
    assert closure == replayed_closure
    assert closure["verdict"] == "all_projected"
    assert closure["source_count"] == 4
    assert closure["outcome_counts"] == {
        "projected": 4,
        "pending": 0,
        "failed": 0,
    }
    assert [item["source_id"] for item in closure["outcomes"]] == [
        "source-000001",
        "source-000002",
        "source-000003",
        "source-000004",
    ]
    assert closure["outcomes"][-1]["projection"]["id"] == (
        "projection-source-000004-v1"
    )
    assert closure["outcomes"][-1]["reserved_projection"] == frozen["projection"]
    assert before_closure == after_closure

    ledger_entries, ledger_error = START_INTAKE._validate_ledger(
        work / "ledger.jsonl"
    )
    assert ledger_error is None
    duplicate_path_entries = json.loads(json.dumps(ledger_entries))
    duplicate_path_entries[14]["source"]["stored_path"] = duplicate_path_entries[6][
        "source"
    ]["stored_path"]
    duplicate_path_entries[14]["source"]["sha256"] = duplicate_path_entries[6][
        "source"
    ]["sha256"]
    duplicate_inventory, duplicate_error = (
        START_INTAKE._source_projection_closure_inventory(
            work, duplicate_path_entries
        )
    )
    assert duplicate_inventory is None
    assert duplicate_error["stopped"] == "invalid source projection ledger"
    assert "duplicate artifact path" in duplicate_error["why"]

    missing_reservation_entries = json.loads(json.dumps(ledger_entries))
    missing_reservation_entries[14]["projection"] = None
    missing_inventory, missing_error = (
        START_INTAKE._source_projection_closure_inventory(
            work, missing_reservation_entries
        )
    )
    assert missing_inventory is None
    assert missing_error["stopped"] == "invalid source projection ledger"
    assert "lost its pending projection reservation" in missing_error["why"]

    additional_projection_path = work / projected["projection"]["path"]
    additional_projection_bytes = additional_projection_path.read_bytes()
    additional_projection_path.write_bytes(b"changed projection bytes")
    changed_projection = START_INTAKE.run_source_projection_closure(work)
    assert changed_projection["status"] == "blocked"
    assert changed_projection["stopped"] == "immutable source projection changed"
    additional_projection_path.write_bytes(additional_projection_bytes)

    state_path = work / "intake-state.json"
    changed_state = json.loads(state_path.read_text())
    changed_state["pending_additional_source"]["lineage"]["question_round"] = 99
    state_path.write_text(json.dumps(changed_state, indent=2, sort_keys=True) + "\n")
    changed_lineage = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE
    )
    assert changed_lineage["status"] == "blocked"
    assert changed_lineage["stopped"] == "invalid ledger"


def test_utf8_additional_source_fills_its_reserved_projection_verbatim(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    projection_answers = iter(_projection_answers(contract=7))
    START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(projection_answers),
        output_fn=lambda _message: None,
    )
    verification_answers = iter(_verification_answers(1))
    START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verification_answers),
        output_fn=lambda _message: None,
    )
    START_INTAKE.run_clarification_boundary(work)
    question_answers = iter([
        "fresh-questioner",
        "pytest-gap-question",
        "local_file",
        "Which local file contains the missing readable evidence?",
    ])
    START_INTAKE.run_gap_clarification(
        work,
        input_fn=lambda _prompt: next(question_answers),
        output_fn=lambda _message: None,
    )
    supplied = tmp_path / "reference.txt"
    supplied.write_text("plain text reference\n")
    frozen = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_file=supplied,
    )
    ledger_before = (work / "ledger.jsonl").read_bytes()

    result = START_INTAKE.run_clarification_boundary(work)
    ledger_after = (work / "ledger.jsonl").read_bytes()

    assert result["boundary"] == "additional_source_projection_complete"
    assert result["status"] == "ready_for_projection_assessment"
    assert result["stopped"] == "additional_source_projection_recorded"
    assert frozen["projection"]["status"] == "pending"
    assert result["reserved_projection"] == frozen["projection"]
    assert result["projection"]["id"] == frozen["projection"]["id"]
    assert result["projection"]["method"] == "verbatim_utf8"
    assert result["projection"]["coverage"]["status"] == "complete"
    assert (work / result["projection"]["path"]).read_bytes() == supplied.read_bytes()
    assert len(ledger_after.decode("utf-8").splitlines()) == len(
        ledger_before.decode("utf-8").splitlines()
    ) + 1

    closure = START_INTAKE.run_source_projection_closure(work)
    assert closure["verdict"] == "all_projected"
    assert closure["outcome_counts"] == {
        "projected": 4,
        "pending": 0,
        "failed": 0,
    }
    assert closure["outcomes"][-1]["outcome"] == "projected"
    assert closure["outcomes"][-1]["projection"]["id"] == frozen["projection"]["id"]
    complete_qualification = {
        "qualification": "readable_projection_complete",
        "projection": {"sha256": "a" * 64},
        "coverage": {"remaining_gap_count": 0},
        "remaining_gaps": [],
    }
    disposition, disposition_error = START_INTAKE._clarification_terminal_disposition(
        {
            "decision": "clarification_complete",
            "remaining_current_gap_count": 0,
        },
        complete_qualification,
        closure,
    )
    assert disposition_error is None
    assert disposition["disposition"] == "first_layer_complete"
    assert (work / "ledger.jsonl").read_bytes() == ledger_after


def test_url_typed_question_freezes_and_projects_one_additional_public_url(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    projection_answers = iter(_projection_answers(contract=7))
    START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(projection_answers),
        output_fn=lambda _message: None,
    )
    verification_answers = iter(_verification_answers(1))
    START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verification_answers),
        output_fn=lambda _message: None,
    )
    START_INTAKE.run_clarification_boundary(work)
    question_answers = iter([
        "fresh-questioner",
        "pytest-gap-question",
        "url",
        "Which public URL contains the missing readable evidence?",
    ])
    waiting = START_INTAKE.run_gap_clarification(
        work,
        input_fn=lambda _prompt: next(question_answers),
        output_fn=lambda _message: None,
    )
    assert waiting["question"]["answer_type"] == "url"
    content = "URL follow-up evidence π\n".encode("utf-8")
    connection = _URLConnection(
        _URLResponse(200, [("Content-Type", "text/plain")], content)
    )
    monkeypatch.setattr(
        START_INTAKE.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (START_INTAKE.socket.AF_INET, START_INTAKE.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    monkeypatch.setattr(
        START_INTAKE, "_url_connection", lambda *_args: connection
    )

    operator_messages: list[str] = []
    frozen = START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda _prompt: "https://example.test/follow-up.txt",
        output_fn=operator_messages.append,
    )
    ledger_after_freeze = (work / "ledger.jsonl").read_bytes()
    monkeypatch.setattr(
        START_INTAKE,
        "_fetch_public_url",
        lambda *_args: (_ for _ in ()).throw(AssertionError("URL was fetched again")),
    )
    replayed = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_url="https://example.test/follow-up.txt",
    )
    completed = START_INTAKE.run_clarification_boundary(work)

    assert replayed == frozen
    assert frozen["status"] == "ready_for_projection"
    assert operator_messages == [
        "Question: Which public URL contains the missing readable evidence?",
        "Answer type: one public HTTP(S) URL",
    ]
    assert frozen["source"]["kind"] == "url"
    assert frozen["source"]["provided_url"] == (
        "https://example.test/follow-up.txt"
    )
    assert frozen["projection"]["status"] == "pending"
    assert completed["boundary"] == "additional_source_projection_complete"
    assert completed["reserved_projection"] == frozen["projection"]
    assert completed["projection"]["id"] == frozen["projection"]["id"]
    assert completed["projection"]["method"] == "verbatim_utf8"
    assert (work / completed["projection"]["path"]).read_bytes() == content
    assert completed["lineage"] == frozen["lineage"]
    closure = START_INTAKE.run_source_projection_closure(work)
    assert closure["verdict"] == "all_projected"
    assert closure["outcome_counts"] == {
        "projected": 4,
        "pending": 0,
        "failed": 0,
    }
    assert len((work / "ledger.jsonl").read_bytes().splitlines()) == (
        len(ledger_after_freeze.splitlines()) + 1
    )


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
            "answer_type": "operator_text",
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


def test_follow_up_question_round_shape_is_complete_unique_bound_and_new() -> None:
    gaps = []
    for index in (1, 2):
        gaps.append({
            "projection_sha256": "a" * 64,
            "collection": "elements",
            "kind": "element",
            "id": f"element-{index:06d}",
            "record_sha256": str(index) * 64,
            "follow_up_of": {
                "question": {
                    "id": f"gap-clarification-answer-{index:06d}",
                    "asks": f"What was hidden in area {index}?",
                },
                "assessment": {
                    "verdict": "does_not_resolve_gap",
                    "reason": "The answer did not identify the hidden value.",
                },
            },
        })
    questions = [
        {
            "id": f"gap-clarification-round-000002-question-{index:06d}",
            "asks": f"What exact value appears in area {index}?",
            "answer_type": "operator_text",
            "answers_gap": {
                key: gaps[index - 1][key]
                for key in (
                    "projection_sha256", "collection", "kind", "id", "record_sha256"
                )
            },
        }
        for index in (1, 2)
    ]
    valid = {"round": 2, "gaps": gaps, "questions": questions}

    assert START_INTAKE._validate_follow_up_question_round_shape(
        valid, gaps, 2
    ) is None
    missing = json.loads(json.dumps(valid))
    missing["questions"].pop()
    reordered = json.loads(json.dumps(valid))
    reordered["questions"].reverse()
    invented = json.loads(json.dumps(valid))
    invented["questions"][0]["answers_gap"]["id"] = "element-invented"
    repeated = json.loads(json.dumps(valid))
    repeated["questions"][0]["asks"] = gaps[0]["follow_up_of"]["question"]["asks"]
    for changed in (missing, reordered, invented, repeated):
        assert START_INTAKE._validate_follow_up_question_round_shape(
            changed, gaps, 2
        ) is not None


def test_follow_up_round_engine_replays_bound_prior_context(tmp_path: Path) -> None:
    projection = {
        "scan_regions": [],
        "elements": [{
            "id": "element-000001",
            "kind": "dashboard metric",
            "region": [10, 10, 50, 50],
            "status": "gap",
            "content": "",
            "gap_reason": "The exact value is unreadable.",
        }],
        "relationships": [],
    }
    projection_path = tmp_path / "projection.json"
    projection_path.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n")
    projection_sha256 = START_INTAKE._digest_bytes(projection_path.read_bytes())
    gaps = START_INTAKE.gap_clarification.select_gaps(
        projection, projection_sha256
    )
    gaps[0]["follow_up_of"] = {
        "question_round": 1,
        "question": {
            "id": "gap-clarification-answer-000001",
            "asks": "Is the value $100?",
        },
        "answer": "Yes.",
        "assessment": {
            "verdict": "does_not_resolve_gap",
            "reason": "The answer assumes a value that is not readable.",
        },
    }
    answers = iter([
        "fresh-follow-up-questioner",
        "pytest-follow-up",
        "operator_text",
        "What exact value should replace the unreadable metric?",
    ])
    result = START_INTAKE.gap_clarification.run_round(
        tmp_path / "round-000002",
        projection_path=projection_path,
        projection_sha256=projection_sha256,
        purpose=REAL_PURPOSE,
        gaps=gaps,
        round_number=2,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    validated, _, _ = START_INTAKE.gap_clarification.validate_round(
        tmp_path / "round-000002",
        projection_path=projection_path,
        projection_sha256=projection_sha256,
        purpose=REAL_PURPOSE,
        gaps=gaps,
        round_number=2,
    )

    assert validated == result
    assert result["round"] == 2
    assert result["gaps"][0]["follow_up_of"]["answer"] == "Yes."
    assert result["questions"] == [{
        "id": "gap-clarification-round-000002-question-000001",
        "asks": "What exact value should replace the unreadable metric?",
        "answer_type": "operator_text",
        "answers_gap": {
            "projection_sha256": projection_sha256,
            "collection": "elements",
            "kind": "element",
            "id": "element-000001",
            "record_sha256": gaps[0]["record_sha256"],
        },
    }]
    operator_ready = START_INTAKE._follow_up_gap_question_round_ready_result(
        {
            "intake_id": "intake-test",
            "follow_up_gap_question_round": {
                "round": 2,
                "question_count": 1,
                "questions": result["questions"],
            },
        },
        tmp_path,
    )
    assert operator_ready["question_count"] == 1
    assert "questions" not in operator_ready


def test_prepared_round_n_interview_persists_answers_and_rejects_changed_result(
    tmp_path: Path,
) -> None:
    projection = {
        "scan_regions": [],
        "elements": [
            {
                "id": f"element-{index:06d}",
                "kind": "metric",
                "region": [index * 20, 0, (index + 1) * 20, 20],
                "status": "gap",
                "content": "",
                "gap_reason": "The value is unreadable.",
            }
            for index in (1, 2)
        ],
        "relationships": [],
    }
    projection_path = tmp_path / "projection.json"
    projection_path.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n")
    projection_sha256 = START_INTAKE._digest_bytes(projection_path.read_bytes())
    gaps = START_INTAKE.gap_clarification.select_gaps(
        projection, projection_sha256
    )
    for index, gap in enumerate(gaps, 1):
        gap["follow_up_of"] = {
            "question_round": 1,
            "question": {"id": f"question-{index}", "asks": f"Is value {index} $100?"},
            "answer": "Yes.",
            "assessment": {
                "verdict": "does_not_resolve_gap",
                "reason": "The answer does not identify visible evidence.",
            },
        }
    round_number = 2
    round_dir = tmp_path / "gap-question-rounds" / "round-000002"
    answers = iter([
        "fresh-reader", "pytest",
        "operator_text",
        "What exact value should replace the first unreadable metric?",
        "operator_text",
        "What exact value should replace the second unreadable metric?",
    ])
    result = START_INTAKE.gap_clarification.run_round(
        round_dir,
        projection_path=projection_path,
        projection_sha256=projection_sha256,
        purpose=REAL_PURPOSE,
        gaps=gaps,
        round_number=round_number,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    journal = START_INTAKE.gap_clarification._read_journal(
        round_dir / "interview.jsonl"
    )
    journal_sha256 = START_INTAKE._digest_bytes(
        (round_dir / "interview.jsonl").read_bytes()
    )
    result_sha256 = START_INTAKE._digest_bytes(
        (round_dir / "clarification-round.json").read_bytes()
    )
    prior_assessment_sha256 = "b" * 64
    current_projection = {
        "id": "projection-source-000003-v1",
        "source_id": "source-000003",
        "version": 1,
        "path": "projection.json",
        "sha256": projection_sha256,
    }
    source = {
        "id": "source-000003",
        "kind": "image",
        "path": "sources/source-000003.png",
        "sha256": "c" * 64,
    }
    seed = START_INTAKE._ledger_entry(1, "source_projected", {
        "intake_id": "intake-test",
        "source": source,
        "projection": current_projection,
    }, None)
    request = START_INTAKE._ledger_entry(2, "model_follow_up_gap_question_round_requested", {
        "round": round_number,
        "contract": START_INTAKE.gap_clarification.ROUND_CONTRACT,
        "projection_path": "projection.json",
        "projection_sha256": projection_sha256,
        "gap_count": len(gaps),
        "gaps": gaps,
        "prior_assessment_sha256": prior_assessment_sha256,
        "interview_path": "gap-question-rounds/round-000002/interview.jsonl",
        "result_path": "gap-question-rounds/round-000002/clarification-round.json",
    }, seed["entry_sha256"])
    completed = START_INTAKE._ledger_entry(3, "model_follow_up_gap_question_round_completed", {
        "round": round_number,
        "interview_path": "gap-question-rounds/round-000002/interview.jsonl",
        "interview_sha256": journal_sha256,
        "result_path": "gap-question-rounds/round-000002/clarification-round.json",
        "result_sha256": result_sha256,
        "question_count": len(result["questions"]),
        "interview_question_count": sum(item["event"] == "question_asked" for item in journal),
        "answer_count": sum(item["event"] == "answer_recorded" for item in journal),
        "rejected_answer_count": 0,
        "questioner": result["questioner"],
        "gaps": result["gaps"],
        "questions": result["questions"],
    }, request["entry_sha256"])
    prepared = START_INTAKE._ledger_entry(4, "operator_follow_up_question_round_prepared", {
        "round": round_number,
        "question_count": len(result["questions"]),
        "questions": result["questions"],
    }, completed["entry_sha256"])
    state = {
        "intake_id": "intake-test",
        "status": "ready_for_operator_interview",
        "phase": "follow_up_gap_question_round_recorded",
        "waiting_for": None,
        "question": None,
        "ledger_entries": 4,
        "ledger_tail_sha256": prepared["entry_sha256"],
        "first_projection": current_projection,
        "current_projection": current_projection,
        "gap_answer_assessment": {"result_sha256": prior_assessment_sha256},
        "follow_up_gap_question_round": {
            "round": round_number,
            "contract": START_INTAKE.gap_clarification.ROUND_CONTRACT,
            "request_ledger_sequence": 2,
            "projection_path": "projection.json",
            "projection_sha256": projection_sha256,
            "gap_count": len(gaps),
            "gaps": gaps,
            "prior_assessment_sha256": prior_assessment_sha256,
            "interview_sha256": journal_sha256,
            "result_sha256": result_sha256,
            "questioner": result["questioner"],
            "question_count": len(result["questions"]),
            "questions": result["questions"],
        },
    }
    (tmp_path / "sources").mkdir()
    (tmp_path / "projections").mkdir()
    (tmp_path / "sources" / "source-000003.png").write_bytes(b"source image")
    START_INTAKE._write_state(tmp_path / "intake-state.json", state)
    (tmp_path / "ledger.jsonl").write_text(
        "".join(
            json.dumps(entry, sort_keys=True) + "\n"
            for entry in (seed, request, completed, prepared)
        )
    )

    assert START_INTAKE._validate_follow_up_gap_question_round(
        tmp_path, state, [seed, request, completed, prepared], REAL_PURPOSE
    ) is None
    waiting = START_INTAKE._start_prepared_question_round_interview(
        tmp_path, state, [seed, request, completed, prepared], REAL_PURPOSE
    )
    assert waiting["status"] == "needs_operator"
    assert waiting["round"] == round_number
    assert waiting["question"] == result["questions"][0]
    assert waiting["question_count"] == 2
    assert "questions" not in waiting

    entries, ledger_error = START_INTAKE._validate_ledger(tmp_path / "ledger.jsonl")
    assert ledger_error is None
    ledger_before_empty = (tmp_path / "ledger.jsonl").read_bytes()
    empty = START_INTAKE._accept_prepared_question_round_answer(
        tmp_path, state, entries, REAL_PURPOSE, "   "
    )
    assert empty["status"] == "blocked"
    assert (tmp_path / "ledger.jsonl").read_bytes() == ledger_before_empty

    first_answer = START_INTAKE._accept_prepared_question_round_answer(
        tmp_path,
        state,
        entries,
        REAL_PURPOSE,
        "It is $48,000.",
    )
    assert first_answer["status"] == "needs_operator"
    assert first_answer["question"] == result["questions"][1]
    assert first_answer["answered_question_count"] == 1
    assert (tmp_path / "sources" / "source-000004.txt").read_text() == "It is $48,000."
    assert (tmp_path / "projections" / "source-000004-v1.txt").read_text() == "It is $48,000."

    entries, ledger_error = START_INTAKE._validate_ledger(tmp_path / "ledger.jsonl")
    assert ledger_error is None
    answered = START_INTAKE._accept_prepared_question_round_answer(
        tmp_path,
        state,
        entries,
        REAL_PURPOSE,
        "It is $12,000.",
    )
    assert answered["status"] == "ready_for_projection_assessment"
    assert answered["round"] == round_number
    assert answered["answered_question_count"] == 2
    assert (tmp_path / "sources" / "source-000005.txt").read_text() == "It is $12,000."
    assert (tmp_path / "projections" / "source-000005-v1.txt").read_text() == "It is $12,000."
    assert START_INTAKE._digest_bytes(projection_path.read_bytes()) == projection_sha256

    entries, ledger_error = START_INTAKE._validate_ledger(tmp_path / "ledger.jsonl")
    assert ledger_error is None
    assert entries[-4]["lineage"]["question_ledger_sequence"] == 5
    assert entries[-2]["lineage"] == {
        "question_ledger_sequence": 7,
        "question_round": round_number,
        "question_position": 2,
        "original_source_id": "source-000003",
        "original_projection_id": "projection-source-000003-v1",
        "prepared_round_result_sha256": result_sha256,
    }
    assert START_INTAKE._validate_prepared_question_round_interview(
        tmp_path, state, entries, REAL_PURPOSE
    ) is None
    changed_state = json.loads(json.dumps(state))
    changed_state["prepared_question_round_interview"]["original_source_id"] = (
        "source-999999"
    )
    wrong_identity = START_INTAKE._validate_prepared_question_round_interview(
        tmp_path, changed_state, entries, REAL_PURPOSE
    )
    assert wrong_identity["status"] == "blocked"

    first_answer_path = tmp_path / "sources" / "source-000004.txt"
    first_answer_bytes = first_answer_path.read_bytes()
    first_answer_path.write_text("changed answer")
    changed_answer = START_INTAKE._validate_prepared_question_round_interview(
        tmp_path, state, entries, REAL_PURPOSE
    )
    assert changed_answer["status"] == "blocked"
    first_answer_path.write_bytes(first_answer_bytes)
    assert START_INTAKE._validate_prepared_question_round_interview(
        tmp_path, state, entries, REAL_PURPOSE
    ) is None
    ledger_before_duplicate = (tmp_path / "ledger.jsonl").read_bytes()
    duplicate = START_INTAKE._accept_prepared_question_round_answer(
        tmp_path, state, entries, REAL_PURPOSE, "Duplicate answer"
    )
    assert duplicate["status"] == "blocked"
    assert (tmp_path / "ledger.jsonl").read_bytes() == ledger_before_duplicate

    requested_assessment = START_INTAKE._request_prepared_question_round_assessment(
        tmp_path, state, entries
    )
    assert requested_assessment["status"] == "waiting_for_model"
    assert requested_assessment["stopped"] == (
        "assessing_prepared_question_round_answers"
    )
    assert requested_assessment["round"] == round_number
    request_entries, ledger_error = START_INTAKE._validate_ledger(
        tmp_path / "ledger.jsonl"
    )
    assert ledger_error is None
    extra = START_INTAKE._ledger_entry(
        len(request_entries) + 1,
        "unexpected_event",
        {"round": round_number},
        request_entries[-1]["entry_sha256"],
    )
    extra_state = json.loads(json.dumps(state))
    extra_state["ledger_entries"] = len(request_entries) + 1
    extra_state["ledger_tail_sha256"] = extra["entry_sha256"]
    _, _, extra_error = (
        START_INTAKE._validate_prepared_question_round_assessment_request(
            tmp_path, extra_state, [*request_entries, extra]
        )
    )
    assert extra_error == {
        "status": "blocked",
        "stopped": "invalid intake state",
        "why": (
            "the prepared-round assessment request is not the only active ledger event"
        ),
    }
    assessment_answers = iter([
        "fresh-assessor",
        "pytest-round-n",
        "maybe",
        "does_not_resolve_gap",
        "The first answer still does not identify readable evidence.",
        "does_not_resolve_gap",
        "The second answer gives a value without enough identifying context.",
    ])
    START_INTAKE.gap_answer_assessment.run(
        tmp_path / "gap-answer-assessments" / "round-000002",
        bindings=START_INTAKE._prepared_question_round_assessment_bindings(
            tmp_path, state
        )[0],
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(assessment_answers),
        output_fn=lambda _message: None,
    )
    entries, ledger_error = START_INTAKE._validate_ledger(tmp_path / "ledger.jsonl")
    assert ledger_error is None
    assessed = START_INTAKE._consume_prepared_question_round_assessment(
        tmp_path, state, entries, REAL_PURPOSE
    )
    assert assessed["status"] == "ready_for_projection_assessment"
    assert assessed["stopped"] == "prepared_question_round_assessment_recorded"
    assert assessed["round"] == round_number
    assert [item["verdict"] for item in assessed["assessments"]] == [
        "does_not_resolve_gap",
        "does_not_resolve_gap",
    ]
    assert [item["gap"]["id"] for item in assessed["assessments"]] == [
        "element-000001",
        "element-000002",
    ]
    assert START_INTAKE._digest_bytes(projection_path.read_bytes()) == projection_sha256
    entries, ledger_error = START_INTAKE._validate_ledger(tmp_path / "ledger.jsonl")
    assert ledger_error is None
    assert entries[-2]["event"] == "model_gap_answer_assessment_requested"
    assert entries[-1]["event"] == "model_gap_answer_assessment_completed"
    assert entries[-1]["round"] == round_number
    assert entries[-1]["rejected_answer_count"] == 1
    assert START_INTAKE._validate_prepared_question_round_assessment(
        tmp_path, state, entries, REAL_PURPOSE
    ) is None
    parent_projection = json.loads(json.dumps(state["current_projection"]))
    child_projection = {
        **parent_projection,
        "id": "projection-source-000003-v2",
        "version": 2,
        "path": "projection-v2.json",
        "sha256": "d" * 64,
        "parent_projection_id": parent_projection["id"],
    }
    later_state = json.loads(json.dumps(state))
    later_state.update({
        "status": "ready_for_projection_assessment",
        "phase": "gap_resolution_applied",
        "current_projection": child_projection,
        "gap_resolution": {
            "attempt": 1,
            "mode": "assessed_answer",
            "parent_projection": parent_projection,
        },
    })
    assert START_INTAKE._validate_prepared_question_round_interview(
        tmp_path,
        later_state,
        entries,
        REAL_PURPOSE,
        allow_later_phase=True,
    ) is None

    assessment_path = (
        tmp_path
        / "gap-answer-assessments"
        / "round-000002"
        / "assessment.json"
    )
    assessment_bytes = assessment_path.read_bytes()
    changed_assessment = json.loads(assessment_bytes)
    changed_assessment["assessments"][0]["verdict"] = "maybe"
    assessment_path.write_text(
        json.dumps(changed_assessment, indent=2, sort_keys=True) + "\n"
    )
    assessment_tamper = START_INTAKE._validate_prepared_question_round_assessment(
        tmp_path, state, entries, REAL_PURPOSE
    )
    assert assessment_tamper["status"] == "blocked"
    assessment_path.write_bytes(assessment_bytes)
    assert START_INTAKE._validate_prepared_question_round_assessment(
        tmp_path, state, entries, REAL_PURPOSE
    ) is None
    ledger_before_reassessment = (tmp_path / "ledger.jsonl").read_bytes()
    reassessment = START_INTAKE._request_prepared_question_round_assessment(
        tmp_path, state, entries
    )
    assert reassessment["status"] == "blocked"
    assert (tmp_path / "ledger.jsonl").read_bytes() == ledger_before_reassessment

    next_work = tmp_path.parent / f"{tmp_path.name}-next-round"
    shutil.copytree(tmp_path, next_work)
    next_state = json.loads((next_work / "intake-state.json").read_text())
    next_entries, ledger_error = START_INTAKE._validate_ledger(
        next_work / "ledger.jsonl"
    )
    assert ledger_error is None
    requested_next = START_INTAKE._request_follow_up_gap_question_round(
        next_work, next_state, next_entries
    )
    assert requested_next["status"] == "waiting_for_model"
    assert next_state["follow_up_gap_question_round"]["round"] == 3
    assert next_state["follow_up_gap_question_round"]["prior_assessment_round"] == 2
    assert [item["round"] for item in next_state["prepared_question_round_history"]] == [2]
    assert next_state["prepared_question_round_history"][0]["question_round"][
        "result_sha256"
    ] == result_sha256
    next_request_entries, ledger_error = START_INTAKE._validate_ledger(
        next_work / "ledger.jsonl"
    )
    assert ledger_error is None
    assert next_request_entries[-1]["round"] == 3
    assert next_request_entries[-1]["prior_assessment_round"] == 2
    next_ledger_before_repeat = (next_work / "ledger.jsonl").read_bytes()
    repeated_request = START_INTAKE._request_follow_up_gap_question_round(
        next_work, next_state, next_request_entries
    )
    assert repeated_request["status"] == "blocked"
    assert (next_work / "ledger.jsonl").read_bytes() == next_ledger_before_repeat
    round_three_answers = iter([
        "fresh-round-three-questioner",
        "pytest-round-three",
        "operator_text",
        "Which visible evidence identifies the exact first metric value?",
        "operator_text",
        "Which visible evidence identifies the exact second metric value?",
    ])
    round_three_dir = next_work / "gap-question-rounds" / "round-000003"
    next_gaps = next_state["follow_up_gap_question_round"]["gaps"]
    START_INTAKE.gap_clarification.run_round(
        round_three_dir,
        projection_path=next_work / "projection.json",
        projection_sha256=projection_sha256,
        purpose=REAL_PURPOSE,
        gaps=next_gaps,
        round_number=3,
        input_fn=lambda _prompt: next(round_three_answers),
        output_fn=lambda _message: None,
    )
    next_request_entries, ledger_error = START_INTAKE._validate_ledger(
        next_work / "ledger.jsonl"
    )
    assert ledger_error is None
    prepared_next = START_INTAKE._consume_follow_up_gap_question_round(
        next_work, next_state, next_request_entries, REAL_PURPOSE
    )
    assert prepared_next["status"] == "ready_for_operator_interview"
    assert prepared_next["round"] == 3
    next_entries, ledger_error = START_INTAKE._validate_ledger(
        next_work / "ledger.jsonl"
    )
    assert ledger_error is None
    assert START_INTAKE._validate_prepared_question_round_history(
        next_work, next_state, next_entries, REAL_PURPOSE
    ) is None
    archived_result = (
        next_work
        / "gap-question-rounds"
        / "round-000002"
        / "clarification-round.json"
    )
    archived_value = json.loads(archived_result.read_text())
    archived_value["questions"][0]["id"] = "invented-archived-question"
    archived_result.write_text(
        json.dumps(archived_value, indent=2, sort_keys=True) + "\n"
    )
    archived_tamper = START_INTAKE._validate_prepared_question_round_history(
        next_work, next_state, next_entries, REAL_PURPOSE
    )
    assert archived_tamper["status"] == "blocked"

    changed_work = tmp_path.parent / f"{tmp_path.name}-changed-gap"
    shutil.copytree(tmp_path, changed_work)
    changed_state = json.loads((changed_work / "intake-state.json").read_text())
    changed_projection = json.loads(
        (changed_work / "projection.json").read_text()
    )
    changed_projection["elements"][0]["gap_reason"] = (
        "The gap record changed after its assessed answer."
    )
    changed_projection_path = changed_work / "projection-v2.json"
    changed_projection_path.write_text(
        json.dumps(changed_projection, indent=2, sort_keys=True) + "\n"
    )
    changed_state["current_projection"] = {
        **changed_state["current_projection"],
        "id": "projection-source-000003-v2",
        "version": 2,
        "path": "projection-v2.json",
        "sha256": START_INTAKE._digest_bytes(changed_projection_path.read_bytes()),
        "parent_projection_id": changed_state["current_projection"]["id"],
    }
    changed_entries, ledger_error = START_INTAKE._validate_ledger(
        changed_work / "ledger.jsonl"
    )
    assert ledger_error is None
    changed_ledger_before = (changed_work / "ledger.jsonl").read_bytes()
    changed_gap = START_INTAKE._request_follow_up_gap_question_round(
        changed_work, changed_state, changed_entries
    )
    assert changed_gap["status"] == "blocked"
    assert "changed after its failed clarification" in changed_gap["why"]
    assert (changed_work / "ledger.jsonl").read_bytes() == changed_ledger_before

    changed = json.loads((round_dir / "clarification-round.json").read_text())
    changed["questions"][0]["id"] = "invented-question"
    (round_dir / "clarification-round.json").write_text(
        json.dumps(changed, indent=2, sort_keys=True) + "\n"
    )
    blocked = START_INTAKE._validate_follow_up_gap_question_round(
        tmp_path, state, entries, REAL_PURPOSE, allow_interview=True
    )
    assert blocked == {
        "status": "blocked",
        "stopped": "invalid follow-up gap question round",
        "why": "clarification-round-result-changed",
    }


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


def _missing_endpoint_resolution_fixture(tmp_path: Path) -> dict[str, object]:
    inputs = _gap_resolution_fixture(tmp_path)
    projection = json.loads(inputs["projection_path"].read_text())
    relationship = projection["relationships"][0]
    relationship.pop("binding_issue")
    relationship.pop("origin_point")
    relationship.pop("target_point")
    relationship["from_id"] = None
    relationship["to_id"] = "element-000003"
    relationship["participant_id"] = "element-000003"
    inputs["projection_path"].write_text(
        json.dumps(projection, indent=2, sort_keys=True) + "\n"
    )
    inputs["projection_sha256"] = START_INTAKE._digest_bytes(
        inputs["projection_path"].read_bytes()
    )
    clarification = json.loads(inputs["clarification_path"].read_text())
    clarification["gap"] = START_INTAKE.gap_clarification.select_gaps(
        projection, inputs["projection_sha256"]
    )[0]
    identity = {
        key: clarification["gap"][key]
        for key in (
            "projection_sha256", "collection", "kind", "id", "record_sha256"
        )
    }
    clarification["question"]["answers_gap"] = identity
    clarification["assessment_gap"] = json.loads(json.dumps(clarification["gap"]))
    clarification["accepted_assessment"] = {
        "position": 1,
        "question_id": clarification["question"]["id"],
        "gap": identity,
        "answer_source": {
            "id": "source-answer",
            "sha256": inputs["answer_source_sha256"],
        },
        "answer_projection": {
            "id": "projection-answer-v1",
            "sha256": inputs["answer_projection_sha256"],
        },
        "verdict": "resolves_gap",
        "reason": "The answer confirms the locked known target.",
    }
    inputs["clarification_path"].write_text(
        json.dumps(clarification, indent=2, sort_keys=True) + "\n"
    )
    inputs["clarification_sha256"] = START_INTAKE._digest_bytes(
        inputs["clarification_path"].read_bytes()
    )
    return inputs


def _terminal_projection_fixture(
    tmp_path: Path, *, incomplete: bool = False
) -> tuple[dict[str, object], dict[str, object]]:
    regions = START_INTAKE.projection_interview._scan_regions()
    for region in regions:
        region["status"] = "scanned"
    regions[0]["element_ids"] = ["element-000001", "element-000002"]
    elements = [
        {
            "id": "element-000001",
            "kind": "annotation",
            "region": [10, 10, 100, 100],
            "status": "readable",
            "content": "Column AF",
            "gap_reason": "",
            "capture_scope": regions[0]["id"],
            "scan_region_id": regions[0]["id"],
        },
        {
            "id": "element-000002",
            "kind": "field",
            "region": [110, 10, 200, 100],
            "status": "gap" if incomplete else "readable",
            "content": "" if incomplete else "$8,100",
            "gap_reason": "field is obscured" if incomplete else "",
            "capture_scope": regions[0]["id"],
            "scan_region_id": regions[0]["id"],
        },
    ]
    relationships = [{
        "id": "relationship-000001",
        "kind": "annotation_arrow",
        "from_id": "element-000001",
        "to_id": "element-000002",
        "status": "gap" if incomplete else "readable",
        "description": "" if incomplete else "the annotation identifies the field",
        "gap_reason": "arrow endpoint is obscured" if incomplete else "",
        "verified_obligation_id": "obligation-000001",
        "verified_element_id": "element-000001",
    }]
    obligations = [{
        "id": "obligation-000001",
        "element_id": "element-000001",
        "status": "resolved",
        "resolution": "gap" if incomplete else "relationship",
        "relationship_id": "relationship-000001",
    }]
    if incomplete:
        regions[1].update({
            "status": "gap",
            "gap_reason": "source pixels are unreadable",
        })
    projection = {
        "schema_version": START_INTAKE.PROJECTION_INTERVIEW_CONTRACT,
        "source_sha256": "a" * 64,
        "purpose_quote": REAL_PURPOSE,
        "elements": elements,
        "relationships": relationships,
        "relationship_obligations": obligations,
        "scan_regions": regions,
    }
    projection_path = tmp_path / "projection.json"
    projection_path.write_text(
        json.dumps(projection, indent=2, sort_keys=True) + "\n"
    )
    projection_sha256 = START_INTAKE._digest_bytes(projection_path.read_bytes())
    gap_count = sum(
        item["status"] == "gap"
        for collection in (regions, elements, relationships)
        for item in collection
    )
    record = {
        "id": "projection-source-000003-v1",
        "source_id": "source-000003",
        "version": 1,
        "path": "projection.json",
        "sha256": projection_sha256,
        "element_count": len(elements),
        "relationship_count": len(relationships),
        "gap_count": gap_count,
        "coverage": "unassessed",
    }
    return projection, {"first_projection": record, "current_projection": record}


def test_terminal_projection_qualification_proves_complete_or_exact_incomplete(
    tmp_path: Path,
) -> None:
    _, complete_state = _terminal_projection_fixture(tmp_path)
    complete, complete_error = START_INTAKE._terminal_projection_qualification(
        tmp_path, complete_state
    )

    assert complete_error is None
    assert complete["qualification"] == "readable_projection_complete"
    assert complete["coverage"] == {
        "region_count": 16,
        "region_outcome_count": 16,
        "element_count": 2,
        "relationship_count": 1,
        "relationship_obligation_count": 1,
        "closed_relationship_obligation_count": 1,
        "remaining_gap_count": 0,
    }
    assert complete["remaining_gaps"] == []

    incomplete_work = tmp_path / "incomplete"
    incomplete_work.mkdir()
    projection, incomplete_state = _terminal_projection_fixture(
        incomplete_work, incomplete=True
    )
    incomplete, incomplete_error = (
        START_INTAKE._terminal_projection_qualification(
            incomplete_work, incomplete_state
        )
    )

    assert incomplete_error is None
    assert incomplete["qualification"] == "readable_projection_incomplete"
    assert incomplete["coverage"]["remaining_gap_count"] == 3
    assert [
        (gap["collection"], gap["id"])
        for gap in incomplete["remaining_gaps"]
    ] == [
        ("scan_regions", "region-r01-c02"),
        ("elements", "element-000002"),
        ("relationships", "relationship-000001"),
    ]
    assert [gap["record"] for gap in incomplete["remaining_gaps"]] == [
        projection["scan_regions"][1],
        projection["elements"][1],
        projection["relationships"][0],
    ]


def test_zero_gap_selection_is_terminal_evidence_but_cannot_start_questions(
    tmp_path: Path,
) -> None:
    projection, state = _terminal_projection_fixture(tmp_path)
    projection_sha256 = state["current_projection"]["sha256"]

    assert START_INTAKE.gap_clarification.select_gaps(
        projection, projection_sha256
    ) == []
    try:
        START_INTAKE.gap_clarification.require_gaps(
            projection, projection_sha256
        )
    except START_INTAKE.gap_clarification.ClarificationError as error:
        assert str(error) == "clarification-no-gap"
    else:
        raise AssertionError("question creation accepted a zero-gap projection")


def test_terminal_projection_qualification_fails_closed_on_coverage_conflicts(
    tmp_path: Path,
) -> None:
    projection, state = _terminal_projection_fixture(tmp_path)
    projection["scan_regions"] = projection["scan_regions"][1:]
    path = tmp_path / "projection.json"
    path.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n")
    state["current_projection"]["sha256"] = START_INTAKE._digest_bytes(
        path.read_bytes()
    )

    qualification, error = START_INTAKE._terminal_projection_qualification(
        tmp_path, state
    )

    assert qualification is None
    assert error["stopped"] == "terminal_invalid"
    assert error["why"] == "scan-region coverage has 15 outcomes; expected 16"

    _, pending_state = _terminal_projection_fixture(tmp_path)
    pending = json.loads(path.read_text())
    pending["relationship_obligations"][0]["status"] = "pending"
    path.write_text(json.dumps(pending, indent=2, sort_keys=True) + "\n")
    pending_state["current_projection"]["sha256"] = START_INTAKE._digest_bytes(
        path.read_bytes()
    )
    qualification, error = START_INTAKE._terminal_projection_qualification(
        tmp_path, pending_state
    )
    assert qualification is None
    assert error["stopped"] == "terminal_invalid"
    assert "is not closed" in error["why"]

    for case in (
        "duplicated_region",
        "reordered_regions",
        "contradictory_region_element",
        "duplicated_element",
        "changed_projection",
    ):
        case_work = tmp_path / case
        case_work.mkdir()
        candidate, candidate_state = _terminal_projection_fixture(case_work)
        candidate_path = case_work / "projection.json"
        update_identity = True
        if case == "duplicated_region":
            candidate["scan_regions"][1] = json.loads(
                json.dumps(candidate["scan_regions"][0])
            )
        elif case == "reordered_regions":
            candidate["scan_regions"][0], candidate["scan_regions"][1] = (
                candidate["scan_regions"][1],
                candidate["scan_regions"][0],
            )
        elif case == "contradictory_region_element":
            candidate["scan_regions"][0]["element_ids"] = []
        elif case == "duplicated_element":
            candidate["elements"].append(
                json.loads(json.dumps(candidate["elements"][0]))
            )
            candidate_state["current_projection"]["element_count"] = 3
        else:
            update_identity = False
        candidate_path.write_text(
            json.dumps(candidate, indent=2, sort_keys=True) + "\n"
        )
        if not update_identity:
            candidate_path.write_text(candidate_path.read_text() + " ")
        else:
            candidate_state["current_projection"]["sha256"] = (
                START_INTAKE._digest_bytes(candidate_path.read_bytes())
            )

        qualification, error = START_INTAKE._terminal_projection_qualification(
            case_work, candidate_state
        )

        assert qualification is None, case
        assert error["stopped"] == "terminal_invalid", case


def test_clarification_terminal_disposition_is_code_constrained() -> None:
    gap = {"id": "element-000001", "record": {"status": "gap"}}
    closure = {
        "verdict": "all_projected",
        "source_count": 1,
        "outcome_counts": {"projected": 1, "pending": 0, "failed": 0},
        "outcomes": [{
            "source_id": "source-000001",
            "outcome": "projected",
            "reason": None,
            "projection": {"id": "projection-000001", "sha256": "c" * 64},
        }],
    }
    incomplete = {
        "qualification": "readable_projection_incomplete",
        "projection": {"sha256": "a" * 64},
        "coverage": {"remaining_gap_count": 1},
        "remaining_gaps": [gap],
    }
    required, required_error = START_INTAKE._clarification_terminal_disposition(
        {
            "decision": "clarification_complete",
            "remaining_current_gap_count": 1,
        },
        incomplete,
        closure,
    )

    assert required_error is None
    assert required == {
        "disposition": "clarification_required",
        "projection_sha256": "a" * 64,
        "remaining_gap_count": 1,
        "remaining_gaps": [gap],
    }

    complete = {
        "qualification": "readable_projection_complete",
        "projection": {"sha256": "b" * 64},
        "coverage": {"remaining_gap_count": 0},
        "remaining_gaps": [],
    }
    finished, finished_error = START_INTAKE._clarification_terminal_disposition(
        {
            "decision": "clarification_complete",
            "remaining_current_gap_count": 0,
        },
        complete,
        closure,
    )
    assert finished_error is None
    assert finished == {
        "disposition": "first_layer_complete",
        "projection_sha256": "b" * 64,
        "remaining_gap_count": 0,
        "source_count": 1,
        "outcome_counts": {"projected": 1, "pending": 0, "failed": 0},
    }

    invalid, invalid_error = START_INTAKE._clarification_terminal_disposition(
        {
            "decision": "clarification_complete",
            "remaining_current_gap_count": 1,
        },
        complete,
        closure,
    )
    assert invalid is None
    assert invalid_error["stopped"] == "terminal_invalid"

    pending_outcome = {
        "source_id": "source-000002",
        "outcome": "pending",
        "reason": "the frozen source has not yet been converted",
        "projection": None,
    }
    incomplete_closure = {
        "verdict": "conversion_incomplete",
        "source_count": 2,
        "outcome_counts": {"projected": 1, "pending": 1, "failed": 0},
        "outcomes": [closure["outcomes"][0], pending_outcome],
    }
    conversion_required, conversion_error = (
        START_INTAKE._clarification_terminal_disposition(
            {
                "decision": "clarification_complete",
                "remaining_current_gap_count": 0,
            },
            complete,
            incomplete_closure,
        )
    )
    assert conversion_error is None
    assert conversion_required == {
        "disposition": "source_conversion_required",
        "projection_sha256": "b" * 64,
        "remaining_gap_count": 0,
        "source_count": 2,
        "outcome_counts": {"projected": 1, "pending": 1, "failed": 0},
        "incomplete_source_outcomes": [pending_outcome],
    }

    contradictory_closure = json.loads(json.dumps(incomplete_closure))
    contradictory_closure["verdict"] = "all_projected"
    contradicted, contradiction_error = (
        START_INTAKE._clarification_terminal_disposition(
            {
                "decision": "clarification_complete",
                "remaining_current_gap_count": 0,
            },
            complete,
            contradictory_closure,
        )
    )
    assert contradicted is None
    assert contradiction_error["stopped"] == "terminal_invalid"


def test_clarification_continuation_returns_apply_then_complete_without_mutation(
    tmp_path: Path, monkeypatch: object
) -> None:
    original_clarification_continuation = START_INTAKE._clarification_continuation
    inputs = _missing_endpoint_resolution_fixture(tmp_path)
    clarification = json.loads(inputs["clarification_path"].read_text())
    binding = {
        "position": 1,
        "question": clarification["question"],
        "gap": clarification["gap"],
        "answer_source": {
            "id": "source-answer",
            "path": str(inputs["answer_source_path"].relative_to(tmp_path)),
            "sha256": inputs["answer_source_sha256"],
        },
        "answer_projection": {
            "id": "projection-answer-v1",
            "path": str(inputs["answer_projection_path"].relative_to(tmp_path)),
            "sha256": inputs["answer_projection_sha256"],
        },
        "answer": inputs["answer_source_path"].read_text(),
    }
    assessment = {
        **START_INTAKE.gap_answer_assessment._assessment_identity(binding),
        "verdict": "resolves_gap",
        "reason": "The answer identifies the missing endpoint.",
    }
    saved = {
        "result_sha256": "a" * 64,
        "assessments": [assessment],
    }
    state = {
        "first_projection": {
            "id": "projection-source-000003-v1",
            "path": str(inputs["projection_path"].relative_to(tmp_path)),
            "sha256": inputs["projection_sha256"],
        },
        "current_projection": {
            "id": "projection-source-000003-v1",
            "path": str(inputs["projection_path"].relative_to(tmp_path)),
            "sha256": inputs["projection_sha256"],
        },
        "gap_answer_assessment": saved,
        "gap_resolution_history": [],
    }
    monkeypatch.setattr(
        START_INTAKE,
        "_latest_assessed_round",
        lambda *_args: (1, [binding], saved, None),
    )
    monkeypatch.setattr(
        START_INTAKE,
        "_assessment_round_data",
        lambda *_args: ([binding], saved, None),
    )
    state_before = json.loads(json.dumps(state))
    projection_before = inputs["projection_path"].read_bytes()

    apply, error = START_INTAKE._clarification_continuation(tmp_path, state)

    assert error is None
    assert apply["decision"] == "apply_resolving_answer"
    assert apply["assessment_round"] == 1
    assert apply["assessment_position"] == 1
    assert apply["gap"]["id"] == "relationship-000001"
    assert state == state_before
    assert inputs["projection_path"].read_bytes() == projection_before

    seed = START_INTAKE._ledger_entry(
        1, "test_seed", {"intake_id": "intake-test"}, None
    )
    (tmp_path / "ledger.jsonl").write_text(json.dumps(seed, sort_keys=True) + "\n")
    state.update({
        "intake_id": "intake-test",
        "status": "ready_for_projection_assessment",
        "phase": "gap_answer_assessment_recorded",
        "ledger_entries": 1,
        "ledger_tail_sha256": seed["entry_sha256"],
    })
    apply_result = START_INTAKE._execute_clarification_continuation(
        tmp_path, state, [seed]
    )
    assert apply_result["status"] == "waiting_for_model", apply_result
    assert apply_result["stopped"] == "resolving_gap_answer"
    assert state["gap_resolution"]["selected_assessment_round"] == 1
    assert state["gap_resolution"]["selected_assessment_position"] == 1
    ledger_after_apply = (tmp_path / "ledger.jsonl").read_bytes()
    repeated_apply = START_INTAKE._execute_clarification_continuation(
        tmp_path,
        state,
        [seed, json.loads(ledger_after_apply.decode().splitlines()[-1])],
    )
    assert repeated_apply["status"] == "blocked"
    assert (tmp_path / "ledger.jsonl").read_bytes() == ledger_after_apply

    complete_work = tmp_path.parent / f"{tmp_path.name}-complete"
    shutil.copytree(tmp_path, complete_work)
    shutil.rmtree(complete_work / "gap-resolutions")
    consumed = json.loads(json.dumps(state_before))
    consumed.update({
        "intake_id": "intake-test",
        "status": "ready_for_projection_assessment",
        "phase": "gap_resolution_rejected",
        "ledger_entries": 1,
        "ledger_tail_sha256": seed["entry_sha256"],
    })
    consumed["gap_resolution"] = {
        "mode": "assessed_answer",
        "result_sha256": "b" * 64,
        "selected_assessment_round": 1,
        "selected_assessment_position": 1,
    }
    (complete_work / "ledger.jsonl").write_text(
        json.dumps(seed, sort_keys=True) + "\n"
    )
    complete, error = START_INTAKE._clarification_continuation(
        complete_work, consumed
    )
    replay, replay_error = START_INTAKE._clarification_continuation(
        complete_work, consumed
    )

    assert error is None and replay_error is None
    assert complete == replay == {
        "decision": "clarification_complete",
        "assessment_round": 1,
        "remaining_current_gap_count": 1,
    }
    ledger_before_invalid_terminal = (complete_work / "ledger.jsonl").read_bytes()
    invalid_terminal = START_INTAKE._execute_clarification_continuation(
        complete_work, consumed, [seed]
    )
    assert invalid_terminal["stopped"] == "gap resolution retry unavailable"
    assert (complete_work / "ledger.jsonl").read_bytes() == ledger_before_invalid_terminal
    consumed["phase"] = "gap_resolution_applied"
    complete_closure = {
        "verdict": "all_projected",
        "source_count": 1,
        "outcome_counts": {"projected": 1, "pending": 0, "failed": 0},
        "outcomes": [{
            "source_id": "source-000003",
            "outcome": "projected",
            "reason": None,
            "projection": {
                "id": "projection-source-000003-v1",
                "sha256": inputs["projection_sha256"],
            },
        }],
    }
    monkeypatch.setattr(
        START_INTAKE,
        "_source_projection_closure_inventory",
        lambda *_args: (complete_closure, None),
    )
    incomplete_qualification = {
        "qualification": "readable_projection_incomplete",
        "projection": {
            "id": "projection-source-000003-v1",
            "path": str(inputs["projection_path"].relative_to(tmp_path)),
            "sha256": inputs["projection_sha256"],
        },
        "coverage": {"remaining_gap_count": 1},
        "remaining_gaps": [clarification["gap"]],
    }
    monkeypatch.setattr(
        START_INTAKE,
        "_terminal_projection_qualification",
        lambda *_args: (incomplete_qualification, None),
    )
    ledger_before_required = (complete_work / "ledger.jsonl").read_bytes()
    required_result = START_INTAKE._execute_clarification_continuation(
        complete_work, consumed, [seed]
    )
    assert required_result["stopped"] == "clarification_required"
    assert required_result["projection_qualification"] == incomplete_qualification
    assert required_result["source_projection_closure"] == complete_closure
    assert required_result["terminal_disposition"]["disposition"] == (
        "clarification_required"
    )
    assert required_result["gaps"] == [clarification["gap"]]
    assert (complete_work / "ledger.jsonl").read_bytes() == ledger_before_required
    (complete_work / "sources").mkdir(exist_ok=True)
    (complete_work / "sources" / "source-000001.txt").write_text(
        "There is a new intake"
    )
    (complete_work / "sources" / "source-000002.txt").write_text(REAL_PURPOSE)
    next_round_request = {
        "status": "waiting_for_model",
        "stopped": "formulating_follow_up_gap_question_round",
        "work": [{
            "stage": "formulate_follow_up_gap_question_round",
            "command": ["python3", "start_intake.py"],
        }],
    }
    drive_calls = []

    def drive_required_then_questions(*_args: object, **kwargs: object) -> dict:
        drive_calls.append(kwargs)
        if kwargs.get("clarify_gap") is True:
            return next_round_request
        return required_result

    monkeypatch.setattr(START_INTAKE, "drive", drive_required_then_questions)
    required_boundary = START_INTAKE.run_clarification_boundary(complete_work)
    assert required_boundary == {
        **next_round_request,
        "boundary": "needs_model_interview",
    }
    assert drive_calls == [{}, {"clarify_gap": True}]

    complete_decision = {
        "decision": "clarification_complete",
        "assessment_round": 1,
        "remaining_current_gap_count": 0,
    }
    complete_qualification = {
        "qualification": "readable_projection_complete",
        "projection": {
            "id": "projection-source-000003-v1",
            "path": str(inputs["projection_path"].relative_to(tmp_path)),
            "sha256": inputs["projection_sha256"],
        },
        "coverage": {"remaining_gap_count": 0},
        "remaining_gaps": [],
    }
    monkeypatch.setattr(
        START_INTAKE,
        "_clarification_continuation",
        lambda *_args: (complete_decision, None),
    )
    monkeypatch.setattr(
        START_INTAKE,
        "_terminal_projection_qualification",
        lambda *_args: (complete_qualification, None),
    )
    pending_source = {
        "source_id": "source-000004",
        "outcome": "pending",
        "reason": "the frozen source has not yet been converted",
        "projection": None,
    }
    incomplete_closure = {
        "verdict": "conversion_incomplete",
        "source_count": 2,
        "outcome_counts": {"projected": 1, "pending": 1, "failed": 0},
        "outcomes": [complete_closure["outcomes"][0], pending_source],
    }
    monkeypatch.setattr(
        START_INTAKE,
        "_source_projection_closure_inventory",
        lambda *_args: (incomplete_closure, None),
    )
    ledger_before_conversion_required = (complete_work / "ledger.jsonl").read_bytes()
    conversion_required = START_INTAKE._execute_clarification_continuation(
        complete_work, consumed, [seed]
    )
    assert conversion_required["stopped"] == "source_conversion_required"
    assert conversion_required["source_projection_closure"] == incomplete_closure
    assert conversion_required["incomplete_source_outcomes"] == [pending_source]
    assert (complete_work / "ledger.jsonl").read_bytes() == (
        ledger_before_conversion_required
    )
    conversion_boundary = START_INTAKE._clarification_boundary_result(
        conversion_required, "source_conversion_required"
    )
    assert conversion_boundary["boundary"] == "source_conversion_required"

    monkeypatch.setattr(
        START_INTAKE,
        "_source_projection_closure_inventory",
        lambda *_args: (
            None,
            START_INTAKE._blocked(
                "immutable source projection changed",
                "projection projection-source-000004-v1 changed",
            ),
        ),
    )
    invalid_closure = START_INTAKE._execute_clarification_continuation(
        complete_work, consumed, [seed]
    )
    assert invalid_closure["stopped"] == "terminal_invalid"
    assert (complete_work / "ledger.jsonl").read_bytes() == (
        ledger_before_conversion_required
    )

    monkeypatch.setattr(
        START_INTAKE,
        "_source_projection_closure_inventory",
        lambda *_args: (complete_closure, None),
    )
    complete_result = START_INTAKE._execute_clarification_continuation(
        complete_work, consumed, [seed]
    )
    assert complete_result["stopped"] == "clarification_continuation_complete"
    assert complete_result["continuation"] == complete_decision
    assert complete_result["projection_qualification"] == complete_qualification
    assert complete_result["source_projection_closure"] == complete_closure
    assert complete_result["terminal_disposition"] == {
        "disposition": "first_layer_complete",
        "projection_sha256": inputs["projection_sha256"],
        "remaining_gap_count": 0,
        "source_count": 1,
        "outcome_counts": {"projected": 1, "pending": 0, "failed": 0},
    }
    completion_ledger = (complete_work / "ledger.jsonl").read_bytes()
    completion_entries, ledger_error = START_INTAKE._validate_ledger(
        complete_work / "ledger.jsonl"
    )
    assert ledger_error is None
    completion_replay = START_INTAKE._execute_clarification_continuation(
        complete_work, consumed, completion_entries
    )
    assert completion_replay == complete_result
    assert (complete_work / "ledger.jsonl").read_bytes() == completion_ledger
    changed_completion = json.loads(json.dumps(consumed))
    changed_completion["clarification_completion"]["terminal_disposition"][
        "remaining_gap_count"
    ] = 1
    changed_completion_error = START_INTAKE._validate_clarification_completion(
        complete_work, changed_completion, completion_entries
    )
    assert changed_completion_error["status"] == "blocked"
    monkeypatch.setattr(
        START_INTAKE, "drive", lambda *_args, **_kwargs: complete_result
    )
    terminal_boundary = START_INTAKE.run_clarification_boundary(complete_work)
    assert terminal_boundary["boundary"] == "clarification_complete"
    assert terminal_boundary["continuation"] == complete_decision
    assert terminal_boundary["projection_qualification"] == complete_qualification
    assert terminal_boundary["terminal_disposition"]["disposition"] == (
        "first_layer_complete"
    )
    monkeypatch.setattr(
        START_INTAKE,
        "_clarification_continuation",
        original_clarification_continuation,
    )

    changed_binding = json.loads(json.dumps(binding))
    changed_binding["gap"]["record_sha256"] = "0" * 64
    changed_assessment = {
        **START_INTAKE.gap_answer_assessment._assessment_identity(changed_binding),
        "verdict": "resolves_gap",
        "reason": "The answer identifies the missing endpoint.",
    }
    changed_saved = {
        "result_sha256": "c" * 64,
        "assessments": [changed_assessment],
    }
    monkeypatch.setattr(
        START_INTAKE,
        "_latest_assessed_round",
        lambda *_args: (1, [changed_binding], changed_saved, None),
    )
    monkeypatch.setattr(
        START_INTAKE,
        "_assessment_round_data",
        lambda *_args: ([changed_binding], changed_saved, None),
    )
    _, changed_error = START_INTAKE._clarification_continuation(tmp_path, state)
    assert changed_error["status"] == "blocked"
    assert "changed after round 1 assessment 1" in changed_error["why"]


def test_latest_assessment_round_rejects_incomplete_duplicate_or_reordered_history(
    tmp_path: Path,
) -> None:
    complete = {
        "round": 2,
        "result_sha256": "a" * 64,
        "assessments": [],
    }
    variants = [
        [{**complete, "result_sha256": None}],
        [complete, {**complete}],
        [{**complete, "round": 2}, {**complete, "round": 4}],
        [{**complete, "round": 3}, {**complete, "round": 2}],
    ]
    for records in variants:
        _, _, _, error = START_INTAKE._latest_assessed_round(
            tmp_path, {"prepared_question_round_assessments": records}
        )
        assert error["status"] == "blocked"


def test_clarification_boundary_rejects_non_clarification_external_work() -> None:
    model = START_INTAKE._clarification_boundary_result(
        {
            "status": "waiting_for_model",
            "stopped": "interviewing_first_projection",
            "work": [{"command": ["python", "projection.py"]}],
        },
        "needs_model_interview",
    )
    operator = START_INTAKE._clarification_boundary_result(
        {
            "status": "needs_operator",
            "stopped": "awaiting_first_source",
            "question": {"id": "first-source", "asks": "Provide a source."},
        },
        "needs_operator_answer",
    )
    assert model["status"] == "blocked"
    assert operator["status"] == "blocked"


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


def test_assessed_answer_resolution_cannot_reassess_or_change_known_endpoint(
    tmp_path: Path,
) -> None:
    inputs = _gap_resolution_fixture(tmp_path)
    projection = json.loads(inputs["projection_path"].read_text())
    relationship = projection["relationships"][0]
    relationship["to_id"] = "element-000003"
    inputs["projection_path"].write_text(
        json.dumps(projection, indent=2, sort_keys=True) + "\n"
    )
    inputs["projection_sha256"] = START_INTAKE._digest_bytes(
        inputs["projection_path"].read_bytes()
    )
    clarification = json.loads(inputs["clarification_path"].read_text())
    clarification["gap"]["projection_sha256"] = inputs["projection_sha256"]
    clarification["gap"]["record"] = relationship
    clarification["gap"]["record_sha256"] = START_INTAKE._digest_bytes(
        json.dumps(relationship, sort_keys=True, separators=(",", ":")).encode()
    )
    gap_identity = {
        key: clarification["gap"][key]
        for key in (
            "projection_sha256", "collection", "kind", "id", "record_sha256"
        )
    }
    clarification["question"]["answers_gap"] = gap_identity
    clarification["accepted_assessment"] = {
        "position": 1,
        "question_id": clarification["question"]["id"],
        "gap": gap_identity,
        "answer_source": {
            "id": "source-answer",
            "sha256": inputs["answer_source_sha256"],
        },
        "answer_projection": {
            "id": "projection-answer-v1",
            "sha256": inputs["answer_projection_sha256"],
        },
        "verdict": "resolves_gap",
        "reason": "The preserved answer selects the specific nested element.",
    }
    inputs["clarification_path"].write_text(
        json.dumps(clarification, indent=2, sort_keys=True) + "\n"
    )
    inputs["clarification_sha256"] = START_INTAKE._digest_bytes(
        inputs["clarification_path"].read_bytes()
    )
    answers = iter([
        "fresh-resolver",
        "pytest-assessed-resolution",
        "unbound-element",
        "element-000001",
        "The specific callout points to the May 16 · ACH field.",
    ])
    messages: list[str] = []

    result = START_INTAKE.gap_resolution.run(
        tmp_path / "assessed-resolution",
        **inputs,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )
    candidate = json.loads(
        (tmp_path / "assessed-resolution" / "verification-candidate.json").read_text()
    )
    journal = [
        json.loads(line)
        for line in (
            tmp_path / "assessed-resolution" / "interview.jsonl"
        ).read_text().splitlines()
    ]

    assert result["verdict"] == "resolves_gap"
    assert result["reason"] == clarification["accepted_assessment"]["reason"]
    assert candidate["elements"] == projection["elements"]
    assert candidate["relationships"][0]["from_id"] == "element-000001"
    assert candidate["relationships"][0]["to_id"] == "element-000003"
    assert candidate["relationships"][0]["target_point"] == [700, 100]
    asked_ids = [
        item["question"]["id"]
        for item in journal
        if item["event"] == "question_asked"
    ]
    assert "resolution_verdict" not in asked_ids
    assert "resolution_reason" not in asked_ids
    assert sum(
        item["event"] == "answer_recorded" and not item["accepted"]
        for item in journal
    ) == 1
    assert "choose one of" in messages[0]

    changed_projection = json.loads(inputs["projection_path"].read_text())
    changed_projection["relationships"][0]["target_point"] = [999, 999]
    inputs["projection_path"].write_text(
        json.dumps(changed_projection, indent=2, sort_keys=True) + "\n"
    )
    inputs["projection_sha256"] = START_INTAKE._digest_bytes(
        inputs["projection_path"].read_bytes()
    )
    changed_clarification = json.loads(inputs["clarification_path"].read_text())
    changed_relationship = changed_projection["relationships"][0]
    changed_clarification["gap"]["projection_sha256"] = inputs[
        "projection_sha256"
    ]
    changed_clarification["gap"]["record"] = changed_relationship
    changed_clarification["gap"]["record_sha256"] = START_INTAKE._digest_bytes(
        json.dumps(
            changed_relationship, sort_keys=True, separators=(",", ":")
        ).encode()
    )
    changed_identity = {
        key: changed_clarification["gap"][key]
        for key in (
            "projection_sha256", "collection", "kind", "id", "record_sha256"
        )
    }
    changed_clarification["question"]["answers_gap"] = changed_identity
    changed_clarification["accepted_assessment"]["gap"] = changed_identity
    inputs["clarification_path"].write_text(
        json.dumps(changed_clarification, indent=2, sort_keys=True) + "\n"
    )
    inputs["clarification_sha256"] = START_INTAKE._digest_bytes(
        inputs["clarification_path"].read_bytes()
    )
    try:
        START_INTAKE.gap_resolution.run(
            tmp_path / "invalid-known-endpoint",
            **inputs,
            purpose=REAL_PURPOSE,
            input_fn=lambda _prompt: "unused",
            output_fn=lambda _message: None,
        )
    except START_INTAKE.gap_resolution.ResolutionError as error:
        assert str(error) == "resolution-known-target-binding-invalid"
    else:
        raise AssertionError("invalid known endpoint was accepted")


def test_assessed_answer_resolution_rebinds_unchanged_gap_to_new_projection(
    tmp_path: Path,
) -> None:
    inputs = _gap_resolution_fixture(tmp_path)
    projection = json.loads(inputs["projection_path"].read_text())
    relationship = projection["relationships"][0]
    relationship["to_id"] = "element-000003"
    inputs["projection_path"].write_text(
        json.dumps(projection, indent=4, sort_keys=True) + "\n"
    )
    inputs["projection_sha256"] = START_INTAKE._digest_bytes(
        inputs["projection_path"].read_bytes()
    )
    clarification = json.loads(inputs["clarification_path"].read_text())
    original_gap = json.loads(json.dumps(clarification["gap"]))
    original_gap["record"] = relationship
    original_gap["record_sha256"] = START_INTAKE._digest_bytes(
        json.dumps(relationship, sort_keys=True, separators=(",", ":")).encode()
    )
    active_gap = json.loads(json.dumps(original_gap))
    active_gap["projection_sha256"] = inputs["projection_sha256"]
    clarification["gap"] = active_gap
    clarification["assessment_gap"] = original_gap
    clarification["question"]["answers_gap"] = {
        key: active_gap[key]
        for key in (
            "projection_sha256", "collection", "kind", "id", "record_sha256"
        )
    }
    clarification["accepted_assessment"] = {
        "position": 2,
        "question_id": clarification["question"]["id"],
        "gap": {
            key: original_gap[key]
            for key in (
                "projection_sha256", "collection", "kind", "id", "record_sha256"
            )
        },
        "answer_source": {
            "id": "source-answer",
            "sha256": inputs["answer_source_sha256"],
        },
        "answer_projection": {
            "id": "projection-answer-v1",
            "sha256": inputs["answer_projection_sha256"],
        },
        "verdict": "resolves_gap",
        "reason": "The preserved answer selects the specific nested element.",
    }
    inputs["clarification_path"].write_text(
        json.dumps(clarification, indent=2, sort_keys=True) + "\n"
    )
    inputs["clarification_sha256"] = START_INTAKE._digest_bytes(
        inputs["clarification_path"].read_bytes()
    )

    answers = iter([
        "fresh-resolver",
        "pytest-retargeted-assessment",
        "element-000001",
        "The specific callout identifies the May 16 payout field.",
    ])
    result = START_INTAKE.gap_resolution.run(
        tmp_path / "retargeted-assessed-resolution",
        **inputs,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    assert result["verdict"] == "resolves_gap"


def test_next_resolution_archives_prior_terminal_before_state_transition(
    tmp_path: Path, monkeypatch: object
) -> None:
    source_path = tmp_path / "sources" / "source-000003"
    source_path.parent.mkdir()
    source_path.write_bytes(b"image")
    parent = {
        "id": "projection-source-000003-v2",
        "path": "projections/source-000003-v2.json",
        "sha256": "b" * 64,
        "version": 2,
    }
    previous = {
        "attempt": 1,
        "mode": "assessed_answer",
        "result_sha256": "c" * 64,
        "selected_assessment_position": 1,
    }
    state = {
        "intake_id": "intake-test",
        "phase": "gap_resolution_applied",
        "current_projection": parent,
        "first_projection": {
            "id": "projection-source-000003-v1",
            "path": "projections/source-000003-v1.json",
            "sha256": "a" * 64,
            "version": 1,
        },
        "gap_resolution": previous,
        "gap_resolution_history": [],
        "first_source": {
            "stored_path": "sources/source-000003",
            "media_type": "image/png",
            "sha256": START_INTAKE._digest_bytes(source_path.read_bytes()),
        },
    }
    binding = {
        "gap": {
            "projection_sha256": parent["sha256"],
            "collection": "relationships",
            "kind": "relationship",
            "id": "relationship-000002",
            "record_sha256": "d" * 64,
            "record": {"id": "relationship-000002"},
        },
        "question": {
            "id": "question-2",
            "answers_gap": {
                "projection_sha256": parent["sha256"],
                "collection": "relationships",
                "kind": "relationship",
                "id": "relationship-000002",
                "record_sha256": "d" * 64,
            },
        },
        "answer_source": {"path": "sources/source-2.txt", "sha256": "e" * 64},
        "answer_projection": {
            "path": "projections/source-2-v1.txt",
            "sha256": "e" * 64,
        },
    }
    assessment = {
        "position": 2,
        "gap": dict(binding["question"]["answers_gap"]),
    }
    monkeypatch.setattr(
        START_INTAKE,
        "_next_resolving_assessed_binding",
        lambda *_args: (binding, assessment, 1, None),
    )
    entries = [{"entry_sha256": "f" * 64} for _ in range(29)]

    result = START_INTAKE._request_gap_resolution(tmp_path, state, entries)

    assert result["stopped"] == "resolving_gap_answer"
    assert state["gap_resolution_history"] == [{
        **previous,
        "terminal_phase": "gap_resolution_applied",
        "output_projection": parent,
    }]
    assert state["gap_resolution"]["attempt"] == 2
    assert state["gap_resolution"]["selected_assessment_round"] == 1
    assert state["gap_resolution"]["parent_projection"] == parent
    assert state["waiting_for"] == "gap-resolutions/attempt-000002/interview.jsonl"
    ledger = [
        json.loads(line)
        for line in (tmp_path / "ledger.jsonl").read_text().splitlines()
    ]
    assert ledger[-1]["selected_assessment_round"] == 1
    attachment, command = CODEX_RUNNER.load_request(tmp_path)
    assert attachment == source_path
    assert command[-1] == "--run-gap-resolution"


def test_rejected_resolution_retries_same_assessment_with_preserved_verifier_evidence(
    tmp_path: Path, monkeypatch: object
) -> None:
    parent = {
        "id": "projection-source-000003-v3",
        "path": "projections/source-000003-v3.json",
        "sha256": "a" * 64,
        "version": 3,
    }
    rejected_candidate = {
        "relationships": [{
            "id": "relationship-000001-resolution-000001",
            "resolution_of": "relationship-000001",
            "from_id": "element-000002",
            "to_id": "element-000003",
        }]
    }
    rejected_verification = {
        "verdict": "not_supported",
        "reason": "The proposed origin is the section, but the answer selects the callout.",
    }
    paths = START_INTAKE._resolution_paths(1)
    candidate_path = tmp_path / paths["candidate_path"]
    verification_path = tmp_path / paths["verification_result_path"]
    candidate_path.parent.mkdir(parents=True)
    verification_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        json.dumps(rejected_candidate, indent=2, sort_keys=True) + "\n"
    )
    verification_path.write_text(
        json.dumps(rejected_verification, indent=2, sort_keys=True) + "\n"
    )
    rejected = {
        "attempt": 1,
        "mode": "assessed_answer",
        "result_sha256": "b" * 64,
        "candidate_sha256": START_INTAKE._digest_bytes(candidate_path.read_bytes()),
        "verification_result_sha256": START_INTAKE._digest_bytes(
            verification_path.read_bytes()
        ),
        "verification_verdict": rejected_verification["verdict"],
        "verification_reason": rejected_verification["reason"],
        "selected_assessment_round": 2,
        "selected_assessment_position": 1,
        "parent_projection": parent,
    }
    binding = {
        "gap": {
            "projection_sha256": parent["sha256"],
            "collection": "relationships",
            "kind": "relationship",
            "id": "relationship-000001",
            "record_sha256": "c" * 64,
            "record": {"id": "relationship-000001"},
        },
        "question": {
            "id": "question-1",
            "answers_gap": {
                "projection_sha256": parent["sha256"],
                "collection": "relationships",
                "kind": "relationship",
                "id": "relationship-000001",
                "record_sha256": "c" * 64,
            },
        },
        "answer_source": {"path": "sources/source-1.txt", "sha256": "d" * 64},
        "answer_projection": {
            "path": "projections/source-1-v1.txt",
            "sha256": "d" * 64,
        },
    }
    assessment = {
        "position": 1,
        "gap": dict(binding["question"]["answers_gap"]),
        "verdict": "resolves_gap",
    }
    state = {
        "intake_id": "intake-test",
        "phase": "gap_resolution_rejected",
        "current_projection": parent,
        "first_projection": parent,
        "gap_resolution": rejected,
        "gap_resolution_history": [],
    }
    monkeypatch.setattr(
        START_INTAKE,
        "_assessed_binding_at_position",
        lambda *_args: (binding, assessment, None),
    )
    seed = START_INTAKE._ledger_entry(
        1, "test_seed", {"intake_id": "intake-test"}, None
    )
    (tmp_path / "ledger.jsonl").write_text(json.dumps(seed) + "\n")

    result = START_INTAKE._execute_clarification_continuation(
        tmp_path, state, [seed]
    )

    assert result["stopped"] == "resolving_gap_answer"
    assert state["gap_resolution_history"] == [{
        **rejected,
        "terminal_phase": "gap_resolution_rejected",
        "output_projection": parent,
    }]
    assert state["gap_resolution"]["attempt"] == 2
    assert state["gap_resolution"]["selected_assessment_round"] == 2
    assert state["gap_resolution"]["selected_assessment_position"] == 1
    assert state["gap_resolution"]["retry_of"]["verification_reason"] == (
        rejected_verification["reason"]
    )
    clarification = json.loads(
        (tmp_path / START_INTAKE._resolution_paths(2)["clarification_path"]).read_text()
    )
    assert clarification["prior_rejection"] == state["gap_resolution"]["retry_of"]
    assert candidate_path.read_bytes() == (
        json.dumps(rejected_candidate, indent=2, sort_keys=True) + "\n"
    ).encode()
    assert verification_path.read_bytes() == (
        json.dumps(rejected_verification, indent=2, sort_keys=True) + "\n"
    ).encode()


def test_retry_resolution_reselects_both_endpoints_through_code_choices(
    tmp_path: Path,
) -> None:
    inputs = _missing_endpoint_resolution_fixture(tmp_path)
    clarification = json.loads(inputs["clarification_path"].read_text())
    clarification["prior_rejection"] = {
        "attempt": 1,
        "candidate_sha256": "a" * 64,
        "resolution_result_sha256": "b" * 64,
        "verification_result_sha256": "c" * 64,
        "verification_verdict": "not_supported",
        "verification_reason": "The rejected proposal kept the wrong locked target.",
        "rejected_relationship": {
            "resolution_of": "relationship-000001",
            "from_id": "element-000001",
            "to_id": "element-000003",
        },
    }
    inputs["clarification_path"].write_text(
        json.dumps(clarification, indent=2, sort_keys=True) + "\n"
    )
    inputs["clarification_sha256"] = START_INTAKE._digest_bytes(
        inputs["clarification_path"].read_bytes()
    )
    answers = iter([
        "fresh-retry-resolver",
        "pytest-retry",
        "element-000001",
        "element-000003",
        "100",
        "100",
        "700",
        "100",
        "The callout points to the exact field.",
    ])

    result = START_INTAKE.gap_resolution.run(
        tmp_path / "retry-resolution",
        **inputs,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    candidate = json.loads(
        (tmp_path / "retry-resolution" / "verification-candidate.json").read_text()
    )
    questions = [
        entry["question"]
        for entry in START_INTAKE.gap_resolution._read_journal(
            tmp_path / "retry-resolution" / "interview.jsonl"
        )
        if entry["event"] == "question_asked"
    ]

    assert result["verdict"] == "resolves_gap"
    assert candidate["relationships"][0]["from_id"] == "element-000001"
    assert candidate["relationships"][0]["to_id"] == "element-000003"
    assert candidate["relationships"][0]["binding_method"] == (
        "verifier_rejection_corrected_with_recorded_endpoints"
    )
    assert questions[2]["choices"] == [
        "element-000001", "element-000002", "element-000003"
    ]
    assert questions[2]["context"]["prior_rejection"]["verification_reason"] == (
        "The rejected proposal kept the wrong locked target."
    )


def test_linked_rejected_resolution_retry_is_one_logical_assessment_consumption() -> None:
    rejected = {
        "attempt": 4,
        "mode": "assessed_answer",
        "selected_assessment_round": 2,
        "selected_assessment_position": 1,
        "candidate_sha256": "a" * 64,
        "result_sha256": "b" * 64,
        "verification_result_sha256": "c" * 64,
        "verification_verdict": "not_supported",
        "verification_reason": "The proposed endpoint is wrong.",
        "accepted_assessment_sha256": "d" * 64,
        "operator_answer_source_sha256": "e" * 64,
        "operator_answer_projection_sha256": "e" * 64,
    }
    retry = {
        **rejected,
        "attempt": 5,
        "candidate_sha256": "f" * 64,
        "result_sha256": "1" * 64,
        "verification_result_sha256": "2" * 64,
        "verification_verdict": "supported",
        "verification_reason": "The corrected endpoints are visible.",
        "retry_of": {
            "attempt": 4,
            "candidate_sha256": rejected["candidate_sha256"],
            "resolution_result_sha256": rejected["result_sha256"],
            "verification_result_sha256": rejected[
                "verification_result_sha256"
            ],
            "verification_verdict": rejected["verification_verdict"],
            "verification_reason": rejected["verification_reason"],
        },
    }

    identities, error = START_INTAKE._consumed_assessment_identities(
        [rejected, retry]
    )

    assert error is None
    assert identities == {(2, 1)}

    unlinked = dict(retry)
    unlinked.pop("retry_of")
    identities, error = START_INTAKE._consumed_assessment_identities(
        [rejected, unlinked]
    )
    assert identities is None
    assert error == "an assessed answer was consumed more than once"

    changed_reason = json.loads(json.dumps(retry))
    changed_reason["retry_of"]["verification_reason"] = "changed"
    identities, error = START_INTAKE._consumed_assessment_identities(
        [rejected, changed_reason]
    )
    assert identities is None
    assert error == "an assessed answer was consumed more than once"


def test_archived_rejected_resolution_is_selected_when_its_gap_remains_current(
    tmp_path: Path, monkeypatch: object
) -> None:
    current_gap = {
        "projection_sha256": "f" * 64,
        "collection": "relationships",
        "kind": "relationship",
        "id": "relationship-000030",
        "record_sha256": "a" * 64,
    }
    assessment = {
        "position": 4,
        "question_id": "question-4",
        "gap": dict(current_gap),
        "verdict": "resolves_gap",
    }
    assessment_sha256 = START_INTAKE._digest_bytes(
        json.dumps(assessment, sort_keys=True, separators=(",", ":")).encode()
    )
    rejected = {
        "attempt": 3,
        "mode": "assessed_answer",
        "terminal_phase": "gap_resolution_rejected",
        "selected_assessment_position": 4,
        "accepted_assessment_sha256": assessment_sha256,
        "gap_id": "relationship-000030",
        "verification_verdict": "not_supported",
    }
    state = {
        "phase": "gap_resolution_applied",
        "gap_resolution_history": [rejected],
        "gap_resolution": {
            "attempt": 5,
            "mode": "assessed_answer",
            "selected_assessment_round": 2,
            "selected_assessment_position": 1,
            "retry_of": {"attempt": 4},
        },
    }
    monkeypatch.setattr(
        START_INTAKE,
        "_assessed_binding_at_position",
        lambda *_args: ({"gap": current_gap}, assessment, None),
    )

    selected, decision, error = START_INTAKE._retryable_rejected_resolution(
        tmp_path,
        state,
        {"id": "projection-source-000003-v4"},
        {("relationships", "relationship-000030"): current_gap},
    )

    assert error is None
    assert selected is rejected
    assert decision == {
        "decision": "retry_rejected_resolution",
        "rejected_attempt": 3,
        "assessment_round": 1,
        "assessment_position": 4,
        "gap": current_gap,
    }

    state["gap_resolution"]["retry_of"] = {"attempt": 3}
    selected, decision, error = START_INTAKE._retryable_rejected_resolution(
        tmp_path,
        state,
        {"id": "projection-source-000003-v4"},
        {("relationships", "relationship-000030"): current_gap},
    )
    assert error is None
    assert selected is None and decision is None

    state["gap_resolution"]["retry_of"] = {"attempt": 4}
    selected, decision, error = START_INTAKE._retryable_rejected_resolution(
        tmp_path,
        state,
        {"id": "projection-source-000003-v4"},
        {},
    )
    assert error is None
    assert selected is None and decision is None

def test_next_resolution_distinguishes_same_position_in_later_round(
    tmp_path: Path, monkeypatch: object
) -> None:
    round_one = {"position": 1, "verdict": "resolves_gap"}
    round_two = {"position": 1, "verdict": "resolves_gap"}
    state = {
        "gap_resolution_history": [{
            "selected_assessment_position": 1,
            "result_sha256": "a" * 64,
        }],
        "gap_answer_assessment": {"assessments": [round_one]},
        "prepared_question_round_assessments": [{
            "round": 2,
            "assessments": [round_two],
        }],
    }

    def assessment_round_data(
        _work: Path, _state: dict[str, object], round_number: int
    ) -> tuple[list[dict[str, object]], dict[str, object], None]:
        assessment = round_one if round_number == 1 else round_two
        return [], {"assessments": [assessment]}, None

    selected: list[tuple[int, int]] = []

    def assessed_binding(
        _work: Path,
        _state: dict[str, object],
        round_number: int,
        position: int,
        _parent: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object], None]:
        selected.append((round_number, position))
        return {"round": round_number}, round_two, None

    monkeypatch.setattr(
        START_INTAKE, "_assessment_round_data", assessment_round_data
    )
    monkeypatch.setattr(
        START_INTAKE, "_assessed_binding_at_position", assessed_binding
    )

    binding, assessment, round_number, error = (
        START_INTAKE._next_resolving_assessed_binding(
            tmp_path, state, {"id": "parent"}
        )
    )

    assert error is None
    assert binding == {"round": 2}
    assert assessment == round_two
    assert round_number == 2
    assert selected == [(2, 1)]


def test_later_round_selection_rejects_changed_bound_gap(
    tmp_path: Path, monkeypatch: object
) -> None:
    inputs = _missing_endpoint_resolution_fixture(tmp_path)
    clarification = json.loads(inputs["clarification_path"].read_text())
    assessment = clarification["accepted_assessment"]
    binding = {
        "position": 1,
        "gap": clarification["gap"],
        "question": clarification["question"],
        "answer_source": {
            "id": assessment["answer_source"]["id"],
            "path": str(inputs["answer_source_path"].relative_to(tmp_path)),
            "sha256": inputs["answer_source_sha256"],
        },
        "answer_projection": {
            "id": assessment["answer_projection"]["id"],
            "path": str(inputs["answer_projection_path"].relative_to(tmp_path)),
            "sha256": inputs["answer_projection_sha256"],
        },
    }
    monkeypatch.setattr(
        START_INTAKE,
        "_assessment_round_data",
        lambda *_args: ([binding], {"assessments": [assessment]}, None),
    )
    parent = {
        "id": "projection-source-000003-v4",
        "path": str(inputs["projection_path"].relative_to(tmp_path)),
        "sha256": inputs["projection_sha256"],
    }
    selected, _, error = START_INTAKE._assessed_binding_at_position(
        tmp_path, {}, 2, 1, parent
    )
    assert error is None
    assert selected["gap"]["projection_sha256"] == parent["sha256"]

    projection = json.loads(inputs["projection_path"].read_text())
    projection["relationships"][0]["description"] = "changed after assessment"
    inputs["projection_path"].write_text(
        json.dumps(projection, indent=2, sort_keys=True) + "\n"
    )
    parent["sha256"] = START_INTAKE._digest_bytes(
        inputs["projection_path"].read_bytes()
    )

    _, _, error = START_INTAKE._assessed_binding_at_position(
        tmp_path, {}, 2, 1, parent
    )

    assert error["status"] == "blocked"
    assert "gap relationship-000001 changed in parent projection" in error["why"]


def test_attempt_two_cannot_replay_without_attempt_one_history(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setattr(
        START_INTAKE,
        "_validate_gap_resolution_terminal",
        lambda *_args, **_kwargs: None,
    )
    state = {
        "gap_resolution_history": [],
        "gap_resolution": {"attempt": 2, "mode": "assessed_answer"},
    }

    result = START_INTAKE._validate_gap_resolution_history(
        tmp_path, state, [], REAL_PURPOSE
    )

    assert result == {
        "status": "blocked",
        "stopped": "invalid gap resolution ledger",
        "why": "active attempt received 2; expected 1",
    }


def test_missing_endpoint_resolution_locks_known_identity_and_enforces_bounds(
    tmp_path: Path,
) -> None:
    inputs = _missing_endpoint_resolution_fixture(tmp_path)
    answers = iter([
        "fresh-resolver",
        "pytest-missing-endpoint",
        "invent_participant",
        "use_recorded_element",
        "element-000001",
        "100",
        "400",
        "100",
        "700",
        "300",
        "100",
        "The recorded callout points to the locked field.",
    ])
    messages: list[str] = []

    result = START_INTAKE.gap_resolution.run(
        tmp_path / "missing-endpoint-resolution",
        **inputs,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )
    candidate = json.loads(
        (
            tmp_path
            / "missing-endpoint-resolution"
            / "verification-candidate.json"
        ).read_text()
    )

    assert result["verdict"] == "resolves_gap"
    assert candidate["relationships"][0]["from_id"] == "element-000001"
    assert candidate["relationships"][0]["to_id"] == "element-000003"
    assert candidate["relationships"][0]["origin_point"] == [100, 100]
    assert candidate["relationships"][0]["target_point"] == [700, 100]
    assert candidate["relationships"][0]["resolution_evidence"] == {
        "question_id": "gap-question-000001",
        "operator_answer_source_sha256": inputs["answer_source_sha256"],
        "bound_gap_record_sha256": json.loads(
            inputs["clarification_path"].read_text()
        )["gap"]["record_sha256"],
        "accepted_assessment_sha256": START_INTAKE._digest_bytes(
            json.dumps(
                json.loads(inputs["clarification_path"].read_text())[
                    "accepted_assessment"
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ),
        "locked_known_role": "target",
        "locked_known_element_id": "element-000003",
    }
    assert len(messages) == 3
    assert "choose one of" in messages[0]
    assert "point [100, 400] falls outside" in messages[1]
    assert "point [700, 300] falls outside" in messages[2]


def test_missing_endpoint_resolution_can_capture_one_visible_participant(
    tmp_path: Path,
) -> None:
    inputs = _missing_endpoint_resolution_fixture(tmp_path)
    answers = iter([
        "fresh-resolver",
        "pytest-missing-endpoint-capture",
        "record_visible_element",
        "callout",
        "850",
        "800",
        "950",
        "900",
        "Visible unrecorded callout",
        "900",
        "850",
        "700",
        "100",
        "The captured callout points to the locked field.",
    ])

    START_INTAKE.gap_resolution.run(
        tmp_path / "captured-missing-endpoint",
        **inputs,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    candidate = json.loads(
        (
            tmp_path
            / "captured-missing-endpoint"
            / "verification-candidate.json"
        ).read_text()
    )

    assert candidate["relationships"][0]["from_id"] == "resolution-element-000001"
    assert candidate["relationships"][0]["to_id"] == "element-000003"
    assert candidate["elements"][-1]["content"] == "Visible unrecorded callout"


def test_missing_endpoint_capture_cannot_reuse_locked_known_participant(
    tmp_path: Path,
) -> None:
    inputs = _missing_endpoint_resolution_fixture(tmp_path)
    answers = iter([
        "fresh-resolver",
        "pytest-locked-overlap",
        "record_visible_element",
        "nested callout",
        "600",
        "0",
        "800",
        "200",
        "Visibly distinct nested callout",
        "reuse_recorded_overlap",
        "confirm_distinct_element",
        "650",
        "100",
        "700",
        "100",
        "The distinct nested callout points to the locked field.",
    ])
    messages: list[str] = []

    START_INTAKE.gap_resolution.run(
        tmp_path / "locked-known-overlap",
        **inputs,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )
    candidate = json.loads(
        (
            tmp_path
            / "locked-known-overlap"
            / "verification-candidate.json"
        ).read_text()
    )

    assert len(messages) == 1
    assert "choose one of: confirm_distinct_element" in messages[0]
    assert candidate["relationships"][0]["from_id"] == "resolution-element-000001"
    assert candidate["relationships"][0]["to_id"] == "element-000003"


def test_missing_endpoint_shape_requires_preserved_accepted_assessment(
    tmp_path: Path,
) -> None:
    inputs = _missing_endpoint_resolution_fixture(tmp_path)
    clarification = json.loads(inputs["clarification_path"].read_text())
    clarification.pop("accepted_assessment")
    clarification.pop("assessment_gap")
    inputs["clarification_path"].write_text(
        json.dumps(clarification, indent=2, sort_keys=True) + "\n"
    )
    inputs["clarification_sha256"] = START_INTAKE._digest_bytes(
        inputs["clarification_path"].read_bytes()
    )

    try:
        START_INTAKE.gap_resolution.run(
            tmp_path / "unassessed-missing-endpoint",
            **inputs,
            purpose=REAL_PURPOSE,
            input_fn=lambda _prompt: "unused",
            output_fn=lambda _message: None,
        )
    except START_INTAKE.gap_resolution.ResolutionError as error:
        assert str(error) == (
            "resolution-missing-participant-requires-accepted-assessment"
        )
    else:
        raise AssertionError("unassessed missing endpoint was accepted")


def test_missing_endpoint_resolution_rejects_changed_locked_known_identity(
    tmp_path: Path,
) -> None:
    inputs = _missing_endpoint_resolution_fixture(tmp_path)
    projection = json.loads(inputs["projection_path"].read_text())
    relationship = projection["relationships"][0]
    relationship["participant_id"] = "element-000002"
    inputs["projection_path"].write_text(
        json.dumps(projection, indent=2, sort_keys=True) + "\n"
    )
    inputs["projection_sha256"] = START_INTAKE._digest_bytes(
        inputs["projection_path"].read_bytes()
    )
    clarification = json.loads(inputs["clarification_path"].read_text())
    clarification["gap"]["projection_sha256"] = inputs["projection_sha256"]
    clarification["gap"]["record"] = relationship
    clarification["gap"]["record_sha256"] = START_INTAKE._digest_bytes(
        json.dumps(relationship, sort_keys=True, separators=(",", ":")).encode()
    )
    clarification["assessment_gap"] = json.loads(json.dumps(clarification["gap"]))
    identity = {
        key: clarification["gap"][key]
        for key in (
            "projection_sha256", "collection", "kind", "id", "record_sha256"
        )
    }
    clarification["question"]["answers_gap"] = identity
    clarification["accepted_assessment"]["gap"] = identity
    inputs["clarification_path"].write_text(
        json.dumps(clarification, indent=2, sort_keys=True) + "\n"
    )
    inputs["clarification_sha256"] = START_INTAKE._digest_bytes(
        inputs["clarification_path"].read_bytes()
    )

    try:
        START_INTAKE.gap_resolution.run(
            tmp_path / "changed-locked-known-identity",
            **inputs,
            purpose=REAL_PURPOSE,
            input_fn=lambda _prompt: "unused",
            output_fn=lambda _message: None,
        )
    except START_INTAKE.gap_resolution.ResolutionError as error:
        assert str(error) == "resolution-known-target-binding-invalid"
    else:
        raise AssertionError("changed locked known identity was accepted")


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
