from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from PIL import Image

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
VERIFICATION_STAGE_RUNNER_SCRIPT = (
    ROOT
    / "skills"
    / "info-intake-machinery"
    / "scripts"
    / "run_relationship_verification_with_codex.py"
)
VERIFICATION_STAGE_RUNNER_SPEC = importlib.util.spec_from_file_location(
    "run_relationship_verification_with_codex", VERIFICATION_STAGE_RUNNER_SCRIPT
)
assert VERIFICATION_STAGE_RUNNER_SPEC and VERIFICATION_STAGE_RUNNER_SPEC.loader
VERIFICATION_STAGE_RUNNER = importlib.util.module_from_spec(
    VERIFICATION_STAGE_RUNNER_SPEC
)
VERIFICATION_STAGE_RUNNER_SPEC.loader.exec_module(VERIFICATION_STAGE_RUNNER)
CORRECTION_STAGE_RUNNER_SCRIPT = (
    ROOT
    / "skills"
    / "info-intake-machinery"
    / "scripts"
    / "run_relationship_correction_with_codex.py"
)
CORRECTION_STAGE_RUNNER_SPEC = importlib.util.spec_from_file_location(
    "run_relationship_correction_with_codex", CORRECTION_STAGE_RUNNER_SCRIPT
)
assert CORRECTION_STAGE_RUNNER_SPEC and CORRECTION_STAGE_RUNNER_SPEC.loader
CORRECTION_STAGE_RUNNER = importlib.util.module_from_spec(
    CORRECTION_STAGE_RUNNER_SPEC
)
CORRECTION_STAGE_RUNNER_SPEC.loader.exec_module(CORRECTION_STAGE_RUNNER)
INTAKE_RUNNER_SCRIPT = (
    ROOT / "skills" / "info-intake-machinery" / "scripts" / "run_intake.py"
)
INTAKE_RUNNER_SPEC = importlib.util.spec_from_file_location(
    "run_info_intake", INTAKE_RUNNER_SCRIPT
)
assert INTAKE_RUNNER_SPEC and INTAKE_RUNNER_SPEC.loader
INTAKE_RUNNER = importlib.util.module_from_spec(INTAKE_RUNNER_SPEC)
INTAKE_RUNNER_SPEC.loader.exec_module(INTAKE_RUNNER)
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


def _representative_workbook_bytes(*, missing_workbook: bool = False) -> bytes:
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
</Types>"""
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Dashboard Inputs" sheetId="1" r:id="rId1"/><sheet name="Hidden Logic" sheetId="2" state="hidden" r:id="rId2"/></sheets>
</workbook>"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="worksheet" Target="worksheets/primary.xml"/>
  <Relationship Id="rId2" Type="worksheet" Target="worksheets/hidden.xml"/>
</Relationships>"""
    primary = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Column AC</t></is></c></row><row r="2"><c r="A2"><v>64</v></c><c r="B2"><f>A2/364</f><v>0.175824</v></c></row></sheetData><mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells></worksheet>"""
    hidden = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1"><f>SUM('Dashboard Inputs'!A2)</f><v>64</v></c></row></sheetData></worksheet>"""
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"/>")
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/primary.xml", primary)
        archive.writestr("xl/worksheets/hidden.xml", hidden)
        archive.writestr("xl/customData/metrics.xml", "<metrics><name>unadapted</name></metrics>")
        if not missing_workbook:
            archive.writestr("xl/workbook.xml", workbook)
    return output.getvalue()


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
    Image.new("RGB", (40, 40), "white").save(supplied, format="PNG")
    _advance_to_first_source(work)
    result = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    assert result["status"] == "ready_for_projection"
    assert result["source"]["media_type"] == "image/png"
    return result


def _advance_readable_text_to_terminal(work: Path, supplied: Path) -> dict[str, object]:
    supplied.write_text("FORMULA = 'net_revenue / transactions'\n", encoding="utf-8")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    START_INTAKE.run_qualification_admission(work)
    terminal = START_INTAKE.run_clarification_boundary(work)
    assert terminal["status"] == "first_layer_complete"
    return terminal


def _projection_answers(
    *,
    invalid_status_first: bool = False,
    contract: int = 6,
    second_relationship_obligation: bool = False,
    third_relationship_obligation: bool = False,
) -> list[str]:
    element_status = ["ok", "readable"] if invalid_status_first else ["readable"]
    relationship_status = ["ok", "readable"] if invalid_status_first else ["readable"]
    first_obligation = ["yes"] if contract >= 3 else []
    second_obligation = (
        ["yes"]
        if contract >= 3 and second_relationship_obligation
        else ["no"]
        if contract >= 6
        else ["yes"]
        if contract >= 3
        else []
    )
    required_relationship = (
        [
            *(["contains_claimed_content"] if contract >= 13 else []),
            "use_recorded_endpoint", "visually-connected-to",
            *(["origin"] if contract >= 12 else []),
            "10", "20", "120", "20",
        ]
        if contract >= 5 else
        ["use_recorded_endpoint", "visually-connected-to", "origin", "element-000002"]
        if contract >= 3 else
        ["yes", "visually-connected-to", "element-000001", "element-000002"]
    )
    ownership = ["owned_by_active_core"] if contract >= 11 else []
    third_element = (
        [
            "yes", "unrelated-visible-text", *ownership,
            "120", "130", "220", "220", "readable",
            "An unrelated readable description", "yes",
        ]
        if third_relationship_obligation else []
    )
    explicit_gap = [
        "yes", "obscured-visible-target", *ownership,
        "10", "130", "100", "220", "gap",
        "The target is obscured.", "no",
    ]
    completed_element_scan = (
        [*explicit_gap, *third_element, "no", *(["no"] * 15)]
        if contract >= 4 else ["no"]
    )
    return [
        "test-model", "pytest",
        "yes", "visible-text", *ownership,
        "10", "20", "100", "120", *element_status,
        "A readable description", *first_obligation,
        "yes", "visible-target", *ownership,
        "120", "20", "220", "120", "readable",
        "A readable target", *second_obligation,
        *completed_element_scan,
        *required_relationship,
        *(["supported"] if contract >= 6 else []),
        *relationship_status, "The first element connects to the second.",
        "no",
    ]


def _projection_answers_with_two_element_gaps() -> list[str]:
    return [
        "test-model", "pytest",
        "yes", "visible-text", "owned_by_active_core",
        "10", "20", "100", "120", "readable",
        "A readable description", "yes",
        "yes", "visible-target", "owned_by_active_core",
        "120", "20", "220", "120", "readable",
        "A readable target", "no",
        "yes", "first-obscured-target", "owned_by_active_core",
        "10", "130", "100", "220", "gap",
        "The target is obscured.", "no",
        "yes", "second-obscured-target", "owned_by_active_core",
        "120", "130", "220", "220", "gap",
        "The second target is obscured.", "no",
        "no", *(["no"] * 15),
        "contains_claimed_content",
        "use_recorded_endpoint", "visually-connected-to", "origin",
        "10", "20", "120", "20",
        "supported", "readable", "The first element connects to the second.",
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


def test_replacement_coordinates_are_rejected_at_their_own_axis_boundary(
    tmp_path: Path,
) -> None:
    candidate_path, candidate_sha, verification_path, verification_sha, _, _ = (
        _correction_fixture(tmp_path)
    )
    answers = iter([
        "fresh-corrector", "pytest-correction", "propose_replacement_endpoint", "target",
        "use_recorded_element", "element-000003", "350", "250", "101", "50",
        "Formula defines the correct metric.",
    ])
    messages: list[str] = []

    result = RELATIONSHIP_CORRECTION.run(
        tmp_path / "correction", candidate_path=candidate_path,
        candidate_sha256=candidate_sha, verification_path=verification_path,
        verification_sha256=verification_sha, purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers), output_fn=messages.append,
    )

    relationship = result["corrections"][0]["corrected_relationship"]
    assert relationship["target_point"] == [250, 50]
    assert messages == [
        "Invalid answer: replacement_x: point must fall inside the selected recorded element.",
        "Invalid answer: replacement_y: point must fall inside the selected recorded element.",
    ]


def test_impossible_preserved_x_is_superseded_append_only_before_reasking_x(
    tmp_path: Path,
) -> None:
    candidate_path, candidate_sha, verification_path, verification_sha, _, _ = (
        _correction_fixture(tmp_path)
    )
    candidate, _verification, rejected = RELATIONSHIP_CORRECTION._inputs(
        candidate_path, candidate_sha, verification_path, verification_sha
    )
    attempt = tmp_path / "correction"
    attempt.mkdir()
    journal = attempt / "interview.jsonl"
    state = {
        "model": "", "harness": "", "index": 0, "draft": {}, "corrections": [],
    }
    historical_answers: list[str | int] = [
        "fresh-corrector", "pytest-correction", "propose_replacement_endpoint", "target",
        "use_recorded_element", "element-000003", 350,
    ]
    for answer in historical_answers:
        question = RELATIONSHIP_CORRECTION._question(candidate, rejected, state)
        assert question is not None
        RELATIONSHIP_CORRECTION._append(journal, "question_asked", {"question": question})
        RELATIONSHIP_CORRECTION._append(journal, "answer_recorded", {
            "question_id": question["id"], "raw": str(answer), "accepted": True,
            "parsed": answer, "error": None,
        })
        RELATIONSHIP_CORRECTION._apply_answer(
            candidate, rejected, state, str(question["id"]), answer
        )
    pending = RELATIONSHIP_CORRECTION._question(candidate, rejected, state)
    assert pending is not None and pending["id"] == "replacement_y"
    RELATIONSHIP_CORRECTION._append(journal, "question_asked", {"question": pending})
    preserved_before = journal.read_bytes()
    answers = iter(["250", "50", "Formula defines the correct metric."])

    result = RELATIONSHIP_CORRECTION.run(
        attempt, candidate_path=candidate_path, candidate_sha256=candidate_sha,
        verification_path=verification_path, verification_sha256=verification_sha,
        purpose=REAL_PURPOSE, input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    assert journal.read_bytes().startswith(preserved_before)
    entries = [json.loads(line) for line in journal.read_text().splitlines()]
    superseded = [entry for entry in entries if entry["event"] == "answer_superseded"]
    assert superseded == [{
        **{key: superseded[0][key] for key in (
            "sequence", "event", "previous_entry_sha256", "entry_sha256",
        )},
        "blocked_question_id": "replacement_y",
        "reason": "accepted replacement_x is outside the selected endpoint horizontal bounds",
        "superseded_question_id": "replacement_x",
        "superseded_value": 350,
    }]
    relationship = result["corrections"][0]["corrected_relationship"]
    assert relationship["target_point"] == [250, 50]


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

    assert isinstance(attachment, tuple)
    crop, guide = attachment
    assert crop == (
        work
        / "projection-interviews"
        / "attempt-000001"
        / "region-evidence"
        / "region-r01-c01.png"
    )
    assert guide == crop.with_name("region-r01-c01.ownership.png")
    assert command[-1] == "--run-projection-interview"
    image_paths = [
        argv[index + 1]
        for index, value in enumerate(argv)
        if value == "--image"
    ]
    assert image_paths == [str(crop), str(guide)]
    assert argv[-2] == "--"
    assert command[0] in argv[-1]
    assert "self-contained local controller" in argv[-1]
    assert "do not invoke task intake" in argv[-1]
    assert "red rectangle" not in argv[-1]
    assert "arrow" not in argv[-1]


def test_projection_runner_selects_client_from_the_invoking_host():
    assert CODEX_RUNNER.active_model_client({}) == "codex"
    assert CODEX_RUNNER.active_model_client({"CLAUDECODE": "1"}) == "claude"
    assert CODEX_RUNNER.active_model_client({"MK_CLIENT_KIND": "claude"}) == "claude"


def test_claude_projection_runner_receives_the_same_frozen_sources(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    work.mkdir()
    attachment = work / "source.png"
    attachment.write_bytes(b"image")
    command = ["python3", "start_intake.py", "--run-projection-interview"]

    argv = CODEX_RUNNER.build_claude_argv(
        "/usr/local/bin/claude", work, attachment, command,
    )

    assert argv[:2] == ["/usr/local/bin/claude", "-p"]
    assert str(attachment) in argv[2]
    assert command[0] in argv[2]
    assert argv[argv.index("--allowedTools") + 1] == "Read,Bash"
    assert argv[argv.index("--disallowedTools") + 1] == "Edit,Write,NotebookEdit"


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
    journal = work / "gap-clarifications" / "attempt-000001" / "interview.jsonl"
    journal.parent.mkdir(parents=True)
    attachment.parent.mkdir(parents=True)
    attachment.write_bytes(b"source")
    journal.write_text("")
    (work / "intake-state.json").write_text(json.dumps({
        "waiting_for": "gap-clarifications/attempt-000001/interview.jsonl",
    }))
    first_command = ["python", "start_intake.py", "--run-gap-clarification"]
    second_command = ["python", "start_intake.py", "--run-gap-answer-assessment"]
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
    def load_request(_work: Path) -> tuple[Path, list[str]]:
        if not model_calls:
            return attachment, first_command
        if model_calls == [first_command] and operator_calls:
            return attachment, second_command
        raise CODEX_RUNNER.LaunchError("no visual model stage remains")

    monkeypatch.setattr("builtins.input", lambda _prompt: str(work))
    monkeypatch.setattr(CODEX_RUNNER.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(CODEX_RUNNER, "load_request", load_request)
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


def test_codex_runner_routes_projection_completion_to_verifier_before_clarification(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    attachment = work / "sources" / "source-000003"
    journal = work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text("")
    (work / "intake-state.json").write_text(json.dumps({
        "waiting_for": "projection-interviews/attempt-000001/interview.jsonl",
    }))
    projection_command = ["python", "start_intake.py", "--run-projection-interview"]
    verifier_command = ["python", "start_intake.py", "--run-projection-verification"]
    requests = iter([
        (attachment, projection_command),
        (attachment, verifier_command),
    ])
    model_calls: list[list[str]] = []

    def load_request(_work: Path) -> tuple[Path, list[str]]:
        try:
            return next(requests)
        except StopIteration as error:
            raise CODEX_RUNNER.LaunchError("no visual model stage remains") from error

    def clarification_boundary(_work: Path) -> dict[str, object]:
        assert model_calls == [projection_command, verifier_command]
        return {
            "boundary": "clarification_complete",
            "status": "ready_for_projection_assessment",
            "stopped": "clarification_continuation_complete",
        }

    def run_model(argv: list[str], **_kwargs: object) -> object:
        model_calls.append(argv)
        if argv == projection_command:
            PROJECTION_INTERVIEW._append(journal, "region_outcome_recorded", {
                "region_id": "region-r03-c03",
            })
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(CODEX_RUNNER, "load_request", load_request)
    monkeypatch.setattr(CODEX_RUNNER, "run_clarification_boundary", clarification_boundary)
    monkeypatch.setattr(CODEX_RUNNER.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(CODEX_RUNNER, "_sha256", lambda _path: "a" * 64)
    monkeypatch.setattr(
        CODEX_RUNNER,
        "build_codex_argv",
        lambda _executable, _work, _attachment, command: command,
    )
    monkeypatch.setattr(CODEX_RUNNER.subprocess, "run", run_model)

    assert CODEX_RUNNER.drive_work(work) == 0
    assert model_calls == [projection_command, verifier_command]


@pytest.mark.parametrize(
    ("verdict", "expected_boundary", "expected_status"),
    [
        ("supported", "projection_recorded", "ready_for_projection_assessment"),
        (
            "not_supported",
            "relationship_correction_required",
            "waiting_for_model",
        ),
    ],
)
def test_relationship_verification_launcher_runs_exactly_one_real_stage(
    tmp_path: Path,
    monkeypatch: object,
    verdict: str,
    expected_boundary: str,
    expected_status: str,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    projection_answers = iter(
        _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
    )
    waiting = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(projection_answers),
        output_fn=lambda _message: None,
    )
    assert waiting["stopped"] == "verifying_first_projection"
    model_calls: list[list[str]] = []

    monkeypatch.setattr(
        VERIFICATION_STAGE_RUNNER.CODEX_RUNNER,
        "resolve_model_executable",
        lambda _client: "/usr/bin/codex",
    )

    def run_model(argv: list[str], **_kwargs: object) -> object:
        model_calls.append(argv)
        answers = iter(_verification_answers(1, verdict=verdict))
        result = START_INTAKE.run_first_projection_verification(
            work,
            input_fn=lambda _prompt: next(answers),
            output_fn=lambda _message: None,
        )
        assert result["status"] == expected_status
        return subprocess.CompletedProcess(argv, 0)

    code, payload = VERIFICATION_STAGE_RUNNER.run_one_stage(
        work, model_runner=run_model
    )

    assert code == 0
    assert payload["boundary"] == expected_boundary
    assert payload["status"] == expected_status
    assert len(model_calls) == 1
    ledger_events = [
        json.loads(line)["event"]
        for line in (work / "ledger.jsonl").read_text().splitlines()
    ]
    if verdict == "supported":
        assert ledger_events[-2:] == [
            "model_projection_interview_completed",
            "projection_version_created",
        ]
    else:
        assert "model_projection_interview_completed" not in ledger_events
        assert not (work / "relationship-corrections").exists()


def test_relationship_verification_launcher_refuses_any_other_stage(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    model_calls: list[list[str]] = []
    monkeypatch.setattr(
        VERIFICATION_STAGE_RUNNER.CODEX_RUNNER,
        "resolve_model_executable",
        lambda _client: "/usr/bin/codex",
    )

    code, payload = VERIFICATION_STAGE_RUNNER.run_one_stage(
        work,
        model_runner=lambda argv, **_kwargs: model_calls.append(argv),
    )

    assert code == 3
    assert payload["error"] == "the intake is not waiting for relationship verification"
    assert model_calls == []


def test_relationship_correction_launcher_runs_correction_then_fresh_verification(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    projection_answers = iter(
        _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
    )
    START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(projection_answers),
        output_fn=lambda _message: None,
    )
    verifier_answers = iter(_verification_answers(1, verdict="not_supported"))
    correcting = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verifier_answers),
        output_fn=lambda _message: None,
    )
    assert correcting["stopped"] == "correcting_rejected_relationships"
    model_calls: list[list[str]] = []

    monkeypatch.setattr(
        CORRECTION_STAGE_RUNNER.CODEX_RUNNER,
        "resolve_model_executable",
        lambda _client: "/usr/bin/codex",
    )

    def run_model(argv: list[str], **_kwargs: object) -> object:
        model_calls.append(argv)
        if len(model_calls) == 1:
            answers = iter(_new_endpoint_correction_answers())
            result = START_INTAKE.run_relationship_correction(
                work,
                input_fn=lambda _prompt: next(answers),
                output_fn=lambda _message: None,
            )
            assert result["stopped"] == "verifying_relationship_corrections"
        else:
            answers = iter(_verification_answers(1))
            result = START_INTAKE.run_relationship_correction_verification(
                work,
                input_fn=lambda _prompt: next(answers),
                output_fn=lambda _message: None,
            )
            assert result["stopped"] == "first_projection_recorded"
        return subprocess.CompletedProcess(argv, 0)

    code, payload = CORRECTION_STAGE_RUNNER.run_one_stage(
        work, model_runner=run_model
    )

    assert code == 0
    assert payload["boundary"] == "projection_recorded"
    assert payload["status"] == "ready_for_projection_assessment"
    assert len(model_calls) == 2
    assert model_calls[0] != model_calls[1]
    assert model_calls[0][-1] != model_calls[1][-1]


def test_relationship_correction_launcher_records_a_gap_without_false_verification(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    projection_answers = iter(
        _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
    )
    START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(projection_answers),
        output_fn=lambda _message: None,
    )
    verifier_answers = iter(_verification_answers(1, verdict="not_supported"))
    START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verifier_answers),
        output_fn=lambda _message: None,
    )
    model_calls: list[list[str]] = []
    monkeypatch.setattr(
        CORRECTION_STAGE_RUNNER.CODEX_RUNNER,
        "resolve_model_executable",
        lambda _client: "/usr/bin/codex",
    )

    def run_model(argv: list[str], **_kwargs: object) -> object:
        model_calls.append(argv)
        answers = iter(_gap_correction_answers())
        result = START_INTAKE.run_relationship_correction(
            work,
            input_fn=lambda _prompt: next(answers),
            output_fn=lambda _message: None,
        )
        assert result["stopped"] == "first_projection_recorded"
        return subprocess.CompletedProcess(argv, 0)

    code, payload = CORRECTION_STAGE_RUNNER.run_one_stage(
        work, model_runner=run_model
    )

    assert code == 0
    assert payload["boundary"] == "projection_recorded"
    assert len(model_calls) == 1
    projection = json.loads((work / payload["projection"]["path"]).read_text())
    assert projection["relationships"][0]["status"] == "gap"


def test_relationship_correction_launcher_refuses_any_other_stage(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    model_calls: list[list[str]] = []
    monkeypatch.setattr(
        CORRECTION_STAGE_RUNNER.CODEX_RUNNER,
        "resolve_model_executable",
        lambda _client: "/usr/bin/codex",
    )

    code, payload = CORRECTION_STAGE_RUNNER.run_one_stage(
        work,
        model_runner=lambda argv, **_kwargs: model_calls.append(argv),
    )

    assert code == 3
    assert payload["error"] == "the intake is not waiting for relationship correction"
    assert model_calls == []


def test_relationship_correction_launcher_enters_managed_python_before_imports() -> None:
    completed = subprocess.run(
        ["python3", str(CORRECTION_STAGE_RUNNER_SCRIPT), "unexpected-argument"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout) == {
        "ok": False,
        "error": "this launcher accepts no arguments",
    }
    assert "ModuleNotFoundError" not in completed.stderr


def test_relationship_verification_launcher_enters_managed_python_before_imports() -> None:
    completed = subprocess.run(
        ["python3", str(VERIFICATION_STAGE_RUNNER_SCRIPT), "unexpected-argument"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout) == {
        "ok": False,
        "error": "this launcher accepts no arguments",
    }
    assert "ModuleNotFoundError" not in completed.stderr


def test_zero_input_launcher_conducts_new_intake_one_answer_at_a_time(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "new-intake"
    source = tmp_path / "annotated.png"
    source.write_bytes(b"image")
    answers = iter([
        "new",
        str(work),
        "next_external_boundary",
        "There is a new intake",
        "Make the source annotations AI-readable.",
        "local_file",
        str(source),
    ])
    calls: list[dict[str, object]] = []
    results = iter([
        {
            "status": "needs_operator",
            "question": {
                "id": "intake-purpose",
                "asks": "What information should this intake make AI-readable?",
            },
        },
        {
            "status": "waiting_for_model",
            "stopped": "assessing_intake_purpose",
            "work": [{"command": ["python", "start_intake.py", "--run-purpose-interview"]}],
        },
        {
            "status": "needs_operator",
            "question": {
                "id": "first-source",
                "asks": "Please provide the first source for this intake.",
            },
        },
        {"status": "ready_for_projection", "stopped": "first_source_frozen"},
        {"status": "waiting_for_model", "stopped": "interviewing_first_projection"},
    ])

    def drive(
        selected_work: Path,
        opening: str,
        purpose: str | None = None,
        selected_source: Path | None = None,
        project_source: bool = False,
        **kwargs: object,
    ) -> dict[str, object]:
        calls.append({
            "work": selected_work,
            "opening": opening,
            "purpose": purpose,
            "source": selected_source,
            "project_source": project_source,
            **kwargs,
        })
        return next(results)

    monkeypatch.setattr(INTAKE_RUNNER.start_intake, "drive", drive)
    monkeypatch.setattr(INTAKE_RUNNER, "_run_purpose_model", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        INTAKE_RUNNER.projection_runner,
        "drive_work",
        lambda selected, **_kwargs: 0,
    )

    assert INTAKE_RUNNER.run(input_fn=lambda _prompt: next(answers)) == 0
    assert calls == [
        {
            "work": work,
            "opening": "There is a new intake",
            "purpose": None,
            "source": None,
            "project_source": False,
        },
        {
            "work": work,
            "opening": "There is a new intake",
            "purpose": "Make the source annotations AI-readable.",
            "source": None,
            "project_source": False,
        },
        {
            "work": work,
            "opening": "There is a new intake",
            "purpose": "Make the source annotations AI-readable.",
            "source": None,
            "project_source": False,
        },
        {
            "work": work,
            "opening": "There is a new intake",
            "purpose": "Make the source annotations AI-readable.",
            "source": source,
            "project_source": False,
        },
        {
            "work": work,
            "opening": "There is a new intake",
            "purpose": "Make the source annotations AI-readable.",
            "source": None,
            "project_source": True,
        },
    ]


def test_zero_input_launcher_resumes_preserved_purpose_before_first_source(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "preserved-intake"
    sources = work / "sources"
    sources.mkdir(parents=True)
    opening = "There is a new intake."
    purpose = "Make every annotated relationship AI-readable."
    (sources / "source-000001.txt").write_text(opening)
    (sources / "source-000002.txt").write_text(purpose)
    source = tmp_path / "annotated.png"
    source.write_bytes(b"image")
    answers = iter([
        "resume",
        str(work),
        "next_external_boundary",
        "local_file",
        str(source),
    ])
    calls: list[dict[str, object]] = []
    results = iter([
        {
            "status": "waiting_for_model",
            "stopped": "assessing_intake_purpose",
            "work": [{"command": ["python", "start_intake.py", "--run-purpose-interview"]}],
        },
        {
            "status": "needs_operator",
            "question": {
                "id": "first-source",
                "asks": "Please provide the first source for this intake.",
            },
        },
        {"status": "ready_for_projection", "stopped": "first_source_frozen"},
        {"status": "waiting_for_model", "stopped": "interviewing_first_projection"},
    ])

    def drive(
        selected_work: Path,
        selected_opening: str,
        selected_purpose: str | None = None,
        selected_source: Path | None = None,
        project_source: bool = False,
        **kwargs: object,
    ) -> dict[str, object]:
        calls.append({
            "work": selected_work,
            "opening": selected_opening,
            "purpose": selected_purpose,
            "source": selected_source,
            "project_source": project_source,
            **kwargs,
        })
        return next(results)

    monkeypatch.setattr(INTAKE_RUNNER.start_intake, "drive", drive)
    monkeypatch.setattr(INTAKE_RUNNER, "_run_purpose_model", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        INTAKE_RUNNER.projection_runner,
        "drive_work",
        lambda selected, **_kwargs: 0,
    )

    assert INTAKE_RUNNER.run(input_fn=lambda _prompt: next(answers)) == 0
    assert [call["opening"] for call in calls] == [opening] * 4
    assert [call["purpose"] for call in calls] == [purpose] * 4
    assert calls[2]["source"] == source
    assert calls[3]["project_source"] is True


def test_purpose_model_launcher_has_no_fabricated_visual_attachment(
    tmp_path: Path,
) -> None:
    argv = CODEX_RUNNER.build_codex_argv(
        "/usr/bin/codex",
        tmp_path,
        tuple(),
        ["python", "start_intake.py", "--run-purpose-interview"],
    )

    assert "--image" not in argv
    assert "Assess only the code-bound preserved operator purpose answer." in argv[-1]


def test_zero_input_launcher_rejects_invalid_region_counts_one_at_a_time() -> None:
    answers = iter(["0", "two", "2"])
    messages: list[str] = []

    result = INTAKE_RUNNER._positive_integer(
        "How many completed visual regions should this invocation add?",
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )

    assert result == 2
    assert messages.count(
        "Invalid answer: enter a whole number greater than zero."
    ) == 2


def test_codex_runner_pauses_after_persisted_region_limit_and_resumes(
    tmp_path: Path, monkeypatch: object, capsys: object,
) -> None:
    work = tmp_path / "intake"
    journal = work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text("")
    (work / "intake-state.json").write_text(json.dumps({
        "waiting_for": "projection-interviews/attempt-000001/interview.jsonl",
    }))
    attachments = [work / f"region-{position}.png" for position in range(1, 4)]
    for attachment in attachments:
        attachment.write_bytes(b"region")
    command = ["python", "start_intake.py", "--run-projection-interview"]
    model_calls: list[str] = []

    def load_request(_work: Path) -> tuple[Path, list[str]]:
        count = CODEX_RUNNER._projection_region_outcome_count(journal)
        return attachments[count], command

    def build_argv(
        _executable: str,
        _work: Path,
        attachment: Path,
        _command: list[str],
    ) -> list[str]:
        return ["model", str(attachment)]

    def run_model(argv: list[str], **_kwargs: object) -> object:
        model_calls.append(argv[-1])
        PROJECTION_INTERVIEW._append(journal, "region_outcome_recorded", {
            "region_id": f"region-{len(model_calls)}",
        })
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(CODEX_RUNNER, "load_request", load_request)
    monkeypatch.setattr(CODEX_RUNNER, "build_codex_argv", build_argv)
    monkeypatch.setattr(CODEX_RUNNER.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(CODEX_RUNNER.subprocess, "run", run_model)

    assert CODEX_RUNNER.drive_work(work, projection_region_limit=2) == 0
    first_output = capsys.readouterr().out
    assert model_calls == [str(attachments[0]), str(attachments[1])]
    assert '"projection_regions_completed": 2' in first_output
    assert '"stopped": "projection_region_limit_reached"' in first_output

    assert CODEX_RUNNER.drive_work(work, projection_region_limit=1) == 0
    second_output = capsys.readouterr().out
    assert model_calls == [
        str(attachments[0]), str(attachments[1]), str(attachments[2]),
    ]
    assert '"projection_regions_completed": 1' in second_output
    entries = PROJECTION_INTERVIEW._read_journal(journal)
    assert [entry["sequence"] for entry in entries] == [1, 2, 3]


def test_codex_runner_rejects_invalid_projection_region_limit(
    tmp_path: Path, capsys: object,
) -> None:
    assert CODEX_RUNNER.drive_work(tmp_path, projection_region_limit=0) == 3
    assert "projection region limit must be a positive integer" in (
        capsys.readouterr().out
    )
    assert CODEX_RUNNER.drive_work(tmp_path, projection_region_limit=True) == 3
    assert "projection region limit must be a positive integer" in (
        capsys.readouterr().out
    )


def test_codex_runner_pauses_after_one_persisted_relationship_outcome(
    tmp_path: Path, monkeypatch: object, capsys: object,
) -> None:
    work = tmp_path / "intake"
    journal = work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text("")
    (work / "intake-state.json").write_text(json.dumps({
        "waiting_for": "projection-interviews/attempt-000001/interview.jsonl",
    }))
    attachment = work / "source.png"
    attachment.write_bytes(b"source")
    command = [
        "python", "start_intake.py",
        "--projection-obligation-id", "obligation-000001",
        "--run-projection-interview",
    ]
    model_calls: list[list[str]] = []
    semantic_relationship_count = [0]

    monkeypatch.setattr(
        CODEX_RUNNER, "load_request", lambda _work: (attachment, command)
    )
    monkeypatch.setattr(
        CODEX_RUNNER,
        "build_codex_argv",
        lambda *_args: ["model", "relationship"],
    )
    monkeypatch.setattr(
        CODEX_RUNNER.shutil, "which", lambda _name: "/usr/bin/codex"
    )
    monkeypatch.setattr(
        CODEX_RUNNER, "_projection_relationship_outcome_count",
        lambda _journal: semantic_relationship_count[0],
    )

    def run_model(argv: list[str], **_kwargs: object) -> object:
        model_calls.append(argv)
        semantic_relationship_count[0] += 1
        PROJECTION_INTERVIEW._append(journal, "answer_recorded", {
            "question_id": "relationship_description",
            "raw": "The callout points to the metric.",
            "accepted": True,
            "parsed": "The callout points to the metric.",
            "error": None,
        })
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(CODEX_RUNNER.subprocess, "run", run_model)

    assert CODEX_RUNNER.drive_work(
        work, projection_relationship_limit=1,
    ) == 0

    output = capsys.readouterr().out
    assert model_calls == [["model", "relationship"]]
    assert '"projection_relationships_completed": 1' in output
    assert '"stopped": "projection_relationship_limit_reached"' in output
    assert CODEX_RUNNER._projection_relationship_outcome_count(journal) == 1


def test_codex_runner_continues_when_projection_journal_advances_between_identical_commands(
    tmp_path: Path, monkeypatch: object, capsys: object,
) -> None:
    work = tmp_path / "intake"
    journal = work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text("")
    (work / "intake-state.json").write_text(json.dumps({
        "waiting_for": "projection-interviews/attempt-000001/interview.jsonl",
    }))
    attachment = work / "source.png"
    attachment.write_bytes(b"source")
    command = [
        "python", "start_intake.py",
        "--projection-obligation-id", "obligation-000027",
        "--run-projection-interview",
    ]
    model_calls: list[list[str]] = []
    semantic_relationship_count = [0]

    monkeypatch.setattr(
        CODEX_RUNNER, "load_request", lambda _work: (attachment, command)
    )
    monkeypatch.setattr(
        CODEX_RUNNER,
        "build_codex_argv",
        lambda *_args: ["model", "relationship"],
    )
    monkeypatch.setattr(
        CODEX_RUNNER.shutil, "which", lambda _name: "/usr/bin/codex"
    )
    monkeypatch.setattr(
        CODEX_RUNNER, "_projection_relationship_outcome_count",
        lambda _journal: semantic_relationship_count[0],
    )

    def run_model(argv: list[str], **_kwargs: object) -> object:
        model_calls.append(argv)
        if len(model_calls) == 3:
            semantic_relationship_count[0] += 1
        question_id = (
            "relationship_description"
            if len(model_calls) == 3
            else "element_content_crop_verdict"
        )
        PROJECTION_INTERVIEW._append(journal, "answer_recorded", {
            "question_id": question_id,
            "raw": "supported",
            "accepted": True,
            "parsed": "supported",
            "error": None,
        })
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(CODEX_RUNNER.subprocess, "run", run_model)

    assert CODEX_RUNNER.drive_work(
        work, projection_relationship_limit=1,
    ) == 0

    output = capsys.readouterr().out
    assert model_calls == [
        ["model", "relationship"],
        ["model", "relationship"],
        ["model", "relationship"],
    ]
    assert '"projection_relationships_completed": 1' in output


def test_codex_runner_rejects_invalid_projection_relationship_limit(
    tmp_path: Path, capsys: object,
) -> None:
    assert CODEX_RUNNER.drive_work(
        tmp_path, projection_relationship_limit=0,
    ) == 3
    assert "projection relationship limit must be a positive integer" in (
        capsys.readouterr().out
    )
    assert CODEX_RUNNER.drive_work(
        tmp_path, projection_relationship_limit=True,
    ) == 3
    assert "projection relationship limit must be a positive integer" in (
        capsys.readouterr().out
    )


def test_codex_runner_rejects_an_identical_repeated_model_stage(
    tmp_path: Path, monkeypatch: object, capsys: object,
) -> None:
    work = tmp_path / "intake"
    attachment = work / "sources" / "source-000003"
    journal = work / "gap-clarifications" / "attempt-000001" / "interview.jsonl"
    journal.parent.mkdir(parents=True)
    attachment.parent.mkdir(parents=True)
    attachment.write_bytes(b"source")
    journal.write_text("")
    (work / "intake-state.json").write_text(json.dumps({
        "waiting_for": "gap-clarifications/attempt-000001/interview.jsonl",
    }))
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
        contract=7,
        input_fn=answer,
        output_fn=messages.append,
    )
    resumed = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="a" * 64,
        purpose=REAL_PURPOSE,
        contract=7,
        input_fn=lambda _prompt: (_ for _ in ()).throw(AssertionError("already complete")),
        output_fn=messages.append,
    )

    assert result == resumed
    assert [item["status"] for item in result["elements"]] == [
        "readable", "readable", "gap",
    ]
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
        "element-000001", "element-000002", "element-000003",
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
        contract=7,
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
        contract=7,
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
        contract=7,
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
        contract=7,
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


def test_historical_spatial_identity_refinement_event_still_replays() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["spatial_identity_refinement_enabled"] = True
    state["elements"] = [
        {
            "id": "element-000001", "kind": "annotation",
            "region": [10, 10, 100, 100], "status": "readable",
            "content": "Formula description", "gap_reason": "",
        },
        {
            "id": "element-000002", "kind": "broad metric card",
            "region": [50, 50, 200, 200], "status": "readable",
            "content": "Revenue card", "gap_reason": "",
        },
    ]
    state["current"] = {
        "origin_x": 75,
        "origin_y": 75,
        "origin_point": [75, 75],
        "spatial_identity_issue": {
            "participant": "origin",
            "point": [75, 75],
            "matching_element_ids": ["element-000001", "element-000002"],
            "reason": "no_unique_recorded_element",
        },
        "spatial_intended_element_id": "element-000001",
        "spatial_conflicting_element_id": "element-000002",
        "spatial_conflicting_element_ids": ["element-000002"],
        "refine_left": 120,
        "refine_top": 50,
        "refine_right": 200,
    }

    PROJECTION_INTERVIEW._prepare_spatial_identity_refinement(state, 200)
    pending = state["spatial_identity_refinement_pending"]
    event = pending["event"]
    PROJECTION_INTERVIEW._apply_spatial_identity_refinement(
        state, event, contract=12,
    )

    assert event["element_id"] == "element-000002"
    assert event["previous_element"]["region"] == [50, 50, 200, 200]
    assert event["replacement_element"]["region"] == [120, 50, 200, 200]
    assert state["elements"][1]["region"] == [120, 50, 200, 200]
    assert state["current"]["origin_id"] == "element-000001"


def test_legacy_overlap_migration_restores_bounds_and_preserves_relationship() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    original = {
        "id": "element-000001", "kind": "directional arrow",
        "region": [10, 10, 100, 100], "status": "readable",
        "content": "Visible arrow", "gap_reason": "",
    }
    narrowed = {**original, "region": [10, 10, 49, 100]}
    target = {
        "id": "element-000002", "kind": "dashboard metric",
        "region": [40, 10, 120, 100], "status": "readable",
        "content": "Visible metric", "gap_reason": "",
    }
    refinement = {
        "participant": "origin",
        "intended_element_id": "element-000001",
        "refined_element_id": "element-000001",
        "conflicting_point": [50, 50],
        "previous_element": original,
        "replacement_element": narrowed,
    }
    state["elements"] = [narrowed, target]
    state["relationships"] = [{
        "id": "relationship-000001", "kind": "arrow links to metric",
        "from_id": "element-000001", "to_id": "element-000002",
        "status": "readable", "description": "The arrow points to the metric.",
        "gap_reason": "", "binding_method": "coordinate_unique_containment",
        "origin_point": [25, 50], "target_point": [75, 50],
        "visual_verification": "supported",
        "verified_obligation_id": "obligation-000001",
        "verified_element_id": "element-000001",
        "legacy_binding_refinements": [refinement],
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000001", "element_id": "element-000001",
        "status": "resolved", "resolution": "relationship",
        "relationship_id": "relationship-000001",
    }]

    event = PROJECTION_INTERVIEW._legacy_overlap_binding_migration(state)
    PROJECTION_INTERVIEW._apply_legacy_overlap_binding_migration(state, event)

    assert state["elements"][0] == original
    relationship = state["relationships"][0]
    assert relationship["binding_method"] == (
        "coordinate_selected_identity_and_containment"
    )
    assert relationship["selected_identity_participants"] == {
        "origin": "element-000001",
    }
    assert relationship["legacy_binding_migration"]["action"] == (
        "preserve_selected_identity"
    )
    assert state["relationship_obligations"][0]["status"] == "resolved"


def test_legacy_overlap_migration_restores_bounds_and_reopens_false_gap() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    original = {
        "id": "element-000001", "kind": "directional arrow",
        "region": [10, 10, 100, 100], "status": "readable",
        "content": "Visible arrow", "gap_reason": "",
    }
    narrowed = {**original, "region": [51, 10, 100, 100]}
    target = {
        "id": "element-000002", "kind": "dashboard metric",
        "region": [40, 10, 120, 100], "status": "readable",
        "content": "Visible metric", "gap_reason": "",
    }
    state["elements"] = [narrowed, target]
    state["relationships"] = [{
        "id": "relationship-000001", "kind": "arrow links to metric",
        "from_id": None, "to_id": "element-000002", "status": "gap",
        "description": "", "gap_reason": "Required arrow was not bound.",
        "binding_method": "coordinate_unique_containment",
        "binding_issue": {
            "participant": "relationship", "origin_id": None,
            "target_id": "element-000002",
            "required_element_id": "element-000001",
            "reason": "required_element_not_bound",
        },
        "legacy_binding_refinements": [{
            "participant": "target",
            "intended_element_id": "element-000002",
            "refined_element_id": "element-000001",
            "conflicting_point": [50, 50],
            "previous_element": original,
            "replacement_element": narrowed,
        }],
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000001", "element_id": "element-000001",
        "status": "resolved", "resolution": "gap",
        "relationship_id": "relationship-000001",
    }]

    event = PROJECTION_INTERVIEW._legacy_overlap_binding_migration(state)
    PROJECTION_INTERVIEW._apply_legacy_overlap_binding_migration(state, event)

    assert state["elements"][0] == original
    relationship = state["relationships"][0]
    assert relationship["legacy_binding_migration"]["action"] == (
        "invalidate_false_gap"
    )
    assert relationship["resolution_status"] == "invalidated"
    assert state["relationship_obligations"][0] == {
        "id": "obligation-000001", "element_id": "element-000001",
        "status": "pending", "resolution": None, "relationship_id": None,
    }


def test_required_participant_binding_locks_the_obligated_overlapping_element() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["overlap_identity_selection_enabled"] = True
    state["required_participant_binding_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["elements"] = [
        {
            "id": "element-000001", "kind": "directional arrow",
            "region": [100, 100, 200, 200], "status": "readable",
            "content": "Visible arrow", "gap_reason": "",
        },
        {
            "id": "element-000002", "kind": "dashboard metric",
            "region": [100, 100, 200, 200], "status": "readable",
            "content": "Visible metric", "gap_reason": "",
        },
    ]
    state["relationship_obligations"] = [{
        "id": "obligation-000001", "element_id": "element-000001",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    state["stage"] = "relationship_kind"
    state["current"] = {}

    PROJECTION_INTERVIEW._advance(
        state, "relationship_kind", "arrow links to metric", contract=12,
    )
    assert state["stage"] == "obligation_role"
    PROJECTION_INTERVIEW._advance(
        state, "obligation_role", "origin", contract=12,
    )
    assert state["current"]["origin_id"] == "element-000001"
    assert state["stage"] == "obligation_endpoint_x"
    question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    parsed, error = PROJECTION_INTERVIEW._parse(question, "99", state)
    assert parsed is None
    assert error == (
        "obligation_endpoint_x: coordinate 99 must be inside obligated "
        "element-000001 bounds [100, 100, 200, 200]"
    )
    PROJECTION_INTERVIEW._advance(
        state, "obligation_endpoint_x", 150, contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state, "obligation_endpoint_y", 150, contract=12,
    )
    assert state["current"]["origin_point"] == [150, 150]
    assert state["stage"] == "relationship_target_x"
    state["current"]["target_x"] = 150
    PROJECTION_INTERVIEW._bind_relationship_point(
        state, "target", 150, contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_binding_resolution", "select_recorded_element",
        contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_binding_intended_element", "element-000002",
        contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_visual_verdict", "supported", contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_status", "readable", contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_description", "The arrow points to the metric.",
        contract=12,
    )

    relationship = state["relationships"][0]
    assert relationship["from_id"] == "element-000001"
    assert relationship["to_id"] == "element-000002"
    assert relationship["locked_identity_participants"] == {
        "origin": "element-000001",
    }
    assert relationship["binding_method"] == (
        "required_identity_and_selected_identity_containment"
    )


def test_visual_endpoint_replacement_cannot_replace_the_locked_participant() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["locked_participant_replacement_blocked_enabled"] = True
    state["stage"] = "relationship_visual_endpoint_role"
    state["current"] = {
        "kind": "annotation arrow",
        "origin_id": "element-000047",
        "origin_point": [895, 732],
        "target_id": "element-000049",
        "target_point": [796, 729],
        "locked_identity_participants": {"target": "element-000049"},
    }

    question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )

    assert question["choices"] == ["origin"]
    parsed, error = PROJECTION_INTERVIEW._parse(question, "target", state)
    assert parsed is None
    assert error == (
        "relationship_visual_endpoint_role: choose one of: origin"
    )
    with pytest.raises(
        PROJECTION_INTERVIEW.InterviewError,
        match="locked-relationship-participant-replacement",
    ):
        PROJECTION_INTERVIEW._advance(
            state, "relationship_visual_endpoint_role", "target", contract=12,
        )


def test_locked_participant_activation_recovers_interrupted_replacement_to_gap() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    original_draft = {
        "kind": "annotation arrow",
        "origin_id": "element-000047",
        "origin_x": 895,
        "origin_y": 732,
        "origin_point": [895, 732],
        "locked_identity_participants": {"target": "element-000049"},
    }
    state["relationship_draft"] = dict(original_draft)
    state["current"] = {
        "return_stage": "relationship_target_x",
        "capture_scope": "relationship_endpoint",
    }
    state["stage"] = "element_kind"
    pending = {"id": "element_kind"}
    proposed = {
        "kind": "annotation arrow",
        "required_obligation_id": "obligation-000047",
        "required_element_id": "element-000049",
        "origin": {
            "element_id": "element-000047", "point": [895, 732],
        },
        "target": {
            "element_id": "element-000049", "point": [796, 729],
        },
    }
    history = [{
        "event": "question_asked", "sequence": 4020,
        "question": {
            "id": "relationship_visual_verdict",
            "proposed_relationship": proposed,
        },
    }, {
        "event": "answer_recorded", "sequence": 4021,
        "question_id": "relationship_visual_verdict",
        "accepted": True, "parsed": "not_supported",
    }, {
        "event": "answer_recorded", "sequence": 4023,
        "question_id": "relationship_visual_resolution",
        "accepted": True, "parsed": "record_visible_endpoint",
    }, {
        "event": "answer_recorded", "sequence": 4025,
        "question_id": "relationship_visual_endpoint_role",
        "accepted": True, "parsed": "target",
    }]

    event = PROJECTION_INTERVIEW._locked_participant_replacement_activation(
        state, pending, history, contract=12,
    )
    before = json.loads(json.dumps(event))
    PROJECTION_INTERVIEW._apply_locked_participant_replacement_activation(
        state, event,
    )

    assert event == before
    assert state["locked_participant_replacement_blocked_enabled"] is True
    assert state["relationship_draft"] is None
    assert state["stage"] == "relationship_visual_gap_reason"
    assert state["current"] == {
        **original_draft,
        "target_id": "element-000049",
        "target_x": 796,
        "target_y": 729,
        "target_point": [796, 729],
        "visual_verification": "not_supported",
        "verification_issue": {
            "origin_id": "element-000047",
            "target_id": "element-000049",
            "required_element_id": "element-000049",
            "reason": "visible_connection_not_supported",
        },
    }


def test_locked_participant_activation_does_not_wait_behind_a_pending_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["failed_participant_recovery_enabled"] = True
    state["stage"] = "obligation_resolution"
    pending = {"id": "obligation_resolution"}
    appended: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        PROJECTION_INTERVIEW, "_read_journal", lambda _path: appended,
    )

    def replay(_entries, *, purpose, contract):
        replayed = json.loads(json.dumps(state))
        if appended:
            replayed["locked_participant_replacement_blocked_enabled"] = True
        return replayed, pending, False

    monkeypatch.setattr(PROJECTION_INTERVIEW, "_replay", replay)
    monkeypatch.setattr(
        PROJECTION_INTERVIEW,
        "_append",
        lambda _path, event, payload: appended.append((event, payload)),
    )

    resumed, resumed_pending, completed = PROJECTION_INTERVIEW.prepare_resume(
        tmp_path / "attempt", purpose=REAL_PURPOSE, contract=12,
    )

    assert [event for event, _payload in appended] == [
        "locked_participant_replacement_blocked_enabled",
    ]
    assert resumed["locked_participant_replacement_blocked_enabled"] is True
    assert resumed_pending == pending
    assert completed is False


def test_required_participant_migration_reopens_an_unbound_required_gap() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["relationships"] = [{
        "id": "relationship-000001", "kind": "arrow links to metric",
        "from_id": "element-000003", "to_id": "element-000002",
        "status": "gap", "description": "",
        "gap_reason": "The required arrow was not bound.",
        "binding_method": "coordinate_unique_containment",
        "binding_issue": {
            "participant": "relationship", "origin_id": "element-000003",
            "target_id": "element-000002",
            "required_element_id": "element-000001",
            "reason": "required_element_not_bound",
        },
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000001", "element_id": "element-000001",
        "status": "resolved", "resolution": "gap",
        "relationship_id": "relationship-000001",
    }]

    event = PROJECTION_INTERVIEW._required_participant_gap_migration(state)
    PROJECTION_INTERVIEW._apply_required_participant_gap_migration(state, event)

    assert state["relationships"][0]["resolution_status"] == "invalidated"
    assert state["relationships"][0]["required_participant_migration"] == {
        "action": "reopen_required_participant"
    }
    assert state["relationship_obligations"][0]["status"] == "pending"


def test_projection_attachment_selects_obligation_after_resume_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "intake"
    attempt = work / "projection-interviews" / "attempt-000001"
    source = work / "sources" / "source-000003"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    (source.parent / "source-000002.txt").write_text(
        REAL_PURPOSE, encoding="utf-8",
    )
    prepared = PROJECTION_INTERVIEW._initial_state(contract=12)
    prepared["scan_region_index"] = len(prepared["scan_regions"])
    prepared["relationship_obligations"] = [
        {
            "id": "obligation-000022", "element_id": "element-000022",
            "status": "pending", "resolution": None, "relationship_id": None,
        },
        {
            "id": "obligation-000023", "element_id": "element-000023",
            "status": "pending", "resolution": None, "relationship_id": None,
        },
    ]
    calls: list[str] = []

    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "enable_endpoint_crop_verification",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "enable_existing_participant_crop_verification",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "enable_contextual_endpoint_verification",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "enable_endpoint_context_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "enable_negative_context_replacement",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "enable_rejected_endpoint_reuse_block",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "enable_rejected_endpoint_collision_exclusion",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_endpoint_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_region_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_resume",
        lambda *args, **kwargs: (
            calls.append("prepared") or prepared, None, False,
        ),
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "_read_journal",
        lambda *_args, **_kwargs: pytest.fail(
            "attachment selection replayed stale pre-migration state"
        ),
    )

    attachment, region_id, obligation_id, endpoint_sha256, error = (
        START_INTAKE._projection_model_attachment(
            work,
            source_path=source,
            source_sha256="a" * 64,
            attempt_dir=attempt,
            contract=12,
        )
    )

    assert calls == ["prepared"]
    assert attachment == source
    assert region_id is None
    assert obligation_id == "obligation-000022"
    assert endpoint_sha256 is None
    assert error is None


def test_projection_attachment_uses_full_source_when_relationship_scan_needs_a_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "intake"
    attempt = work / "projection-interviews" / "attempt-000001"
    source = work / "sources" / "source-000003"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    (source.parent / "source-000002.txt").write_text(
        REAL_PURPOSE, encoding="utf-8",
    )
    prepared = PROJECTION_INTERVIEW._initial_state(contract=12)
    prepared["scan_region_index"] = len(prepared["scan_regions"])
    prepared["relationship_obligations"] = []
    for name in (
        "enable_endpoint_crop_verification",
        "enable_existing_participant_crop_verification",
        "enable_contextual_endpoint_verification",
        "enable_endpoint_context_evidence",
        "enable_rejected_endpoint_reuse_block",
        "enable_rejected_endpoint_collision_exclusion",
    ):
        monkeypatch.setattr(
            START_INTAKE.projection_interview, name,
            lambda *args, **kwargs: None,
        )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_endpoint_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_region_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_resume",
        lambda *args, **kwargs: (prepared, None, False),
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "required_participant_replacement_attachments",
        lambda *args, **kwargs: None,
    )

    attachment, region_id, obligation_id, endpoint_sha256, error = (
        START_INTAKE._projection_model_attachment(
            work,
            source_path=source,
            source_sha256="a" * 64,
            attempt_dir=attempt,
            contract=12,
        )
    )

    assert attachment == source
    assert region_id is None
    assert obligation_id is None
    assert endpoint_sha256 is None
    assert error is None

    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "_active_scan_region",
        lambda _state: (_ for _ in ()).throw(
            START_INTAKE.projection_interview.InterviewError(
                "invalid region state"
            )
        ),
    )
    failed = START_INTAKE._projection_model_attachment(
        work,
        source_path=source,
        source_sha256="a" * 64,
        attempt_dir=attempt,
        contract=12,
    )

    assert len(failed) == 5
    assert failed[-1] == {
        "status": "blocked",
        "stopped": "projection region evidence failed",
        "why": "invalid region state",
    }


@pytest.mark.parametrize("stopped", [
    "interviewing_first_projection",
    "verifying_first_projection",
    "correcting_rejected_relationships",
    "verifying_relationship_corrections",
])
def test_clarification_boundary_accepts_primary_projection_model_stages(
    stopped: str,
) -> None:
    result = {
        "status": "waiting_for_model",
        "stopped": stopped,
        "work": [{"command": ["python", "start_intake.py"]}],
    }

    assert START_INTAKE._clarification_boundary_result(
        result, "needs_model_interview",
    ) == {**result, "boundary": "needs_model_interview"}


def test_projection_attachment_skips_unused_replacement_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "intake"
    attempt = work / "projection-interviews" / "attempt-000001"
    source = work / "sources" / "source-000003"
    endpoint = attempt / "endpoint-evidence" / "replacement.png"
    source.parent.mkdir(parents=True)
    endpoint.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    endpoint.write_bytes(b"endpoint")
    (source.parent / "source-000002.txt").write_text(
        REAL_PURPOSE, encoding="utf-8",
    )
    prepared = PROJECTION_INTERVIEW._initial_state(contract=13)
    prepared["scan_region_index"] = len(prepared["scan_regions"])
    prepared["relationship_obligations"] = [{
        "id": "obligation-000023", "element_id": "element-000023",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    for name in (
        "enable_endpoint_crop_verification",
        "enable_existing_participant_crop_verification",
        "enable_contextual_endpoint_verification",
        "enable_endpoint_context_evidence",
        "enable_rejected_endpoint_reuse_block",
        "enable_rejected_endpoint_collision_exclusion",
    ):
        monkeypatch.setattr(
            START_INTAKE.projection_interview, name,
            lambda *args, **kwargs: None,
        )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_endpoint_evidence",
        lambda *args, **kwargs: (endpoint, "b" * 64),
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_region_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_resume",
        lambda *args, **kwargs: (prepared, None, False),
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "required_participant_replacement_attachments",
        lambda *args, **kwargs: pytest.fail(
            "unused replacement fallback was evaluated"
        ),
    )

    attachment, region_id, obligation_id, endpoint_sha256, error = (
        START_INTAKE._projection_model_attachment(
            work,
            source_path=source,
            source_sha256="a" * 64,
            attempt_dir=attempt,
            contract=13,
        )
    )

    assert attachment == endpoint
    assert region_id is None
    assert obligation_id == "obligation-000023"
    assert endpoint_sha256 == "b" * 64
    assert error is None


def test_codex_runner_skips_unused_replacement_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "intake"
    source = work / "sources" / "source-000003"
    endpoint = (
        work / "projection-interviews" / "attempt-000001"
        / "endpoint-evidence" / "replacement.png"
    )
    source.parent.mkdir(parents=True)
    endpoint.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    endpoint.write_bytes(b"endpoint")
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    (source.parent / "source-000002.txt").write_text(
        REAL_PURPOSE, encoding="utf-8",
    )
    (work / "intake-state.json").write_text(json.dumps({
        "status": "waiting_for_model",
        "phase": "interviewing_first_projection",
        "waiting_for": "projection-interviews/attempt-000001/interview.jsonl",
        "projection_interview_contract": 13,
        "first_source": {
            "stored_path": "sources/source-000003",
            "media_type": "image/png",
            "sha256": source_sha256,
        },
    }), encoding="utf-8")
    prepared = PROJECTION_INTERVIEW._initial_state(contract=13)
    prepared["scan_region_index"] = len(prepared["scan_regions"])
    prepared["relationship_obligations"] = [{
        "id": "obligation-000023", "element_id": "element-000023",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    for name in (
        "enable_endpoint_crop_verification",
        "enable_existing_participant_crop_verification",
        "enable_contextual_endpoint_verification",
        "enable_endpoint_context_evidence",
        "enable_endpoint_selector_context",
        "enable_endpoint_identity_context_choice",
        "enable_negative_context_replacement",
        "enable_rejected_endpoint_reuse_block",
        "enable_rejected_endpoint_collision_exclusion",
    ):
        monkeypatch.setattr(
            CODEX_RUNNER.projection_interview, name,
            lambda *args, **kwargs: None,
        )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "prepare_endpoint_evidence",
        lambda *args, **kwargs: (endpoint, "b" * 64),
    )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "prepare_region_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "prepare_resume",
        lambda *args, **kwargs: (prepared, None, False),
    )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "required_participant_replacement_attachments",
        lambda *args, **kwargs: pytest.fail(
            "unused replacement fallback was evaluated"
        ),
    )

    attachment, command = CODEX_RUNNER.load_request(work)

    assert attachment == endpoint
    assert command[-5:] == [
        "--projection-obligation-id", "obligation-000023",
        "--projection-endpoint-evidence-sha256", "b" * 64,
        "--run-projection-interview",
    ]


def test_codex_runner_uses_full_source_for_unbound_relationship_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "intake"
    source = work / "sources" / "source-000003"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    (source.parent / "source-000002.txt").write_text(
        REAL_PURPOSE, encoding="utf-8",
    )
    (work / "intake-state.json").write_text(json.dumps({
        "status": "waiting_for_model",
        "phase": "interviewing_first_projection",
        "waiting_for": "projection-interviews/attempt-000001/interview.jsonl",
        "projection_interview_contract": 12,
        "first_source": {
            "stored_path": "sources/source-000003",
            "media_type": "image/png",
            "sha256": source_sha256,
        },
    }), encoding="utf-8")
    prepared = PROJECTION_INTERVIEW._initial_state(contract=12)
    prepared["scan_region_index"] = len(prepared["scan_regions"])
    prepared["relationship_obligations"] = []
    for name in (
        "enable_endpoint_crop_verification",
        "enable_existing_participant_crop_verification",
        "enable_contextual_endpoint_verification",
        "enable_endpoint_context_evidence",
        "enable_endpoint_selector_context",
        "enable_endpoint_identity_context_choice",
        "enable_negative_context_replacement",
        "enable_rejected_endpoint_reuse_block",
        "enable_rejected_endpoint_collision_exclusion",
    ):
        monkeypatch.setattr(
            CODEX_RUNNER.projection_interview, name,
            lambda *args, **kwargs: None,
        )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "prepare_endpoint_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "prepare_region_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "prepare_resume",
        lambda *args, **kwargs: (prepared, None, False),
    )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "required_participant_replacement_attachments",
        lambda *args, **kwargs: None,
    )

    attachment, command = CODEX_RUNNER.load_request(work)

    assert attachment == source
    assert command[-1] == "--run-projection-interview"
    assert "--projection-region-id" not in command
    assert "--projection-obligation-id" not in command


def test_model_stage_progress_allows_a_declared_journal_before_first_write(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    work.mkdir()
    state_path = work / "intake-state.json"
    state_path.write_text(json.dumps({
        "status": "waiting_for_model",
        "phase": "formulating_gap_question_round",
        "waiting_for": "gap-question-rounds/round-000001/interview.jsonl",
    }), encoding="utf-8")

    progress = CODEX_RUNNER._model_stage_progress(work)

    assert progress == {
        "intake_state_sha256": CODEX_RUNNER._sha256(state_path),
        "model_journal_sha256": None,
    }


def test_projection_interview_allows_no_binding_only_after_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "intake"
    sources = work / "sources"
    sources.mkdir(parents=True)
    (sources / "source-000001.txt").write_text(
        "There is a new intake", encoding="utf-8",
    )
    (sources / "source-000002.txt").write_text(
        REAL_PURPOSE, encoding="utf-8",
    )
    (sources / "source-000003").write_bytes(b"source")
    (work / "intake-state.json").write_text(json.dumps({
        "phase": "interviewing_first_projection",
        "first_source": {
            "stored_path": "sources/source-000003",
            "sha256": "a" * 64,
        },
    }), encoding="utf-8")
    waiting = {
        "status": "waiting_for_model",
        "stopped": "interviewing_first_projection",
    }
    ready = {
        "status": "ready_for_projection_assessment",
        "stopped": "first_projection_recorded",
    }
    drive_results = iter([waiting, ready])
    monkeypatch.setattr(
        START_INTAKE, "drive", lambda *args, **kwargs: next(drive_results),
    )
    monkeypatch.setattr(
        START_INTAKE, "_validate_ledger",
        lambda _path: ([{} for _ in range(7)] + [{"interview_contract": 12}], None),
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "_read_journal",
        lambda _path: [{}],
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "_replay",
        lambda *args, **kwargs: ({}, None, False),
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "_active_scan_region",
        lambda _state: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "_pending_obligation",
        lambda _state: None,
    )
    calls: list[bool] = []
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "run",
        lambda *args, **kwargs: calls.append(True),
    )

    result = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: "no",
        output_fn=lambda _message: None,
        single_region=True,
        region_binding_required=True,
    )

    assert result == ready
    assert calls == [True]

    monkeypatch.setattr(
        START_INTAKE, "drive", lambda *args, **kwargs: waiting,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "_active_scan_region",
        lambda _state: {"id": "region-r01-c01"},
    )
    refused = START_INTAKE.run_first_projection_interview(
        work,
        region_binding_required=True,
    )

    assert refused == {
        "status": "blocked",
        "stopped": "projection invocation invalid",
        "why": "the generated command lost its active projection binding",
    }
    assert calls == [True]


def test_projection_attachment_skips_fallback_during_pending_supersession(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "intake"
    attempt = work / "projection-interviews" / "attempt-000001"
    source = work / "sources" / "source-000003"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    (source.parent / "source-000002.txt").write_text(
        REAL_PURPOSE, encoding="utf-8",
    )
    prepared = PROJECTION_INTERVIEW._initial_state(contract=13)
    prepared["scan_region_index"] = len(prepared["scan_regions"])
    prepared["relationship_obligations"] = [{
        "id": "obligation-000023", "element_id": "element-000023",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    prepared["element_supersession_pending"] = {
        "event": {"superseded_element_id": "element-000023"},
    }
    for name in (
        "enable_endpoint_crop_verification",
        "enable_existing_participant_crop_verification",
        "enable_contextual_endpoint_verification",
        "enable_endpoint_context_evidence",
        "enable_rejected_endpoint_reuse_block",
        "enable_rejected_endpoint_collision_exclusion",
    ):
        monkeypatch.setattr(
            START_INTAKE.projection_interview, name,
            lambda *args, **kwargs: None,
        )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_endpoint_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_region_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "prepare_resume",
        lambda *args, **kwargs: (prepared, None, False),
    )
    monkeypatch.setattr(
        START_INTAKE.projection_interview,
        "required_participant_replacement_attachments",
        lambda *args, **kwargs: pytest.fail(
            "fallback was evaluated during deterministic supersession"
        ),
    )

    attachment, region_id, obligation_id, endpoint_sha256, error = (
        START_INTAKE._projection_model_attachment(
            work,
            source_path=source,
            source_sha256="a" * 64,
            attempt_dir=attempt,
            contract=13,
        )
    )

    assert attachment == source
    assert region_id is None
    assert obligation_id == "obligation-000023"
    assert endpoint_sha256 is None
    assert error is None


def test_codex_runner_skips_fallback_during_pending_supersession(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "intake"
    source = work / "sources" / "source-000003"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    (source.parent / "source-000002.txt").write_text(
        REAL_PURPOSE, encoding="utf-8",
    )
    (work / "intake-state.json").write_text(json.dumps({
        "status": "waiting_for_model",
        "phase": "interviewing_first_projection",
        "waiting_for": "projection-interviews/attempt-000001/interview.jsonl",
        "projection_interview_contract": 13,
        "first_source": {
            "stored_path": "sources/source-000003",
            "media_type": "image/png",
            "sha256": source_sha256,
        },
    }), encoding="utf-8")
    prepared = PROJECTION_INTERVIEW._initial_state(contract=13)
    prepared["scan_region_index"] = len(prepared["scan_regions"])
    prepared["relationship_obligations"] = [{
        "id": "obligation-000023", "element_id": "element-000023",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    prepared["element_supersession_pending"] = {
        "event": {"superseded_element_id": "element-000023"},
    }
    for name in (
        "enable_endpoint_crop_verification",
        "enable_existing_participant_crop_verification",
        "enable_contextual_endpoint_verification",
        "enable_endpoint_context_evidence",
        "enable_endpoint_selector_context",
        "enable_endpoint_identity_context_choice",
        "enable_negative_context_replacement",
        "enable_rejected_endpoint_reuse_block",
        "enable_rejected_endpoint_collision_exclusion",
    ):
        monkeypatch.setattr(
            CODEX_RUNNER.projection_interview, name,
            lambda *args, **kwargs: None,
        )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "prepare_endpoint_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "prepare_region_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "prepare_resume",
        lambda *args, **kwargs: (prepared, None, False),
    )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview,
        "required_participant_replacement_attachments",
        lambda *args, **kwargs: pytest.fail(
            "fallback was evaluated during deterministic supersession"
        ),
    )

    attachment, command = CODEX_RUNNER.load_request(work)

    assert attachment == source
    assert command[-3:] == [
        "--projection-obligation-id", "obligation-000023",
        "--run-projection-interview",
    ]


def test_coordinate_binding_selects_an_overlapping_identity_without_changing_bounds(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    prompts: list[str] = []
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation", "owned_by_active_core",
        "10", "10", "100", "100", "readable",
        "Formula description", "yes",
        "yes", "broad metric card", "owned_by_active_core",
        "50", "50", "200", "200",
        "distinct_unit", "readable", "Revenue card", "no",
        "yes", "dashboard field", "owned_by_active_core",
        "220", "10", "320", "100", "readable",
        "Conversion rate", "no",
        "no", *(["no"] * 15),
        "use_recorded_endpoint", "visible connector", "origin",
        "75", "75", "75", "75",
        "select_recorded_element", "element-000002",
        "supported", "readable",
        "The formula description applies to Conversion rate.",
    ])

    for _ in range(16):
        PROJECTION_INTERVIEW.prepare_region_evidence(
            attempt,
            source_path=source,
            source_sha256=source_sha256,
            purpose=REAL_PURPOSE,
            contract=12,
        )
        projection = PROJECTION_INTERVIEW.run(
            attempt,
            source_sha256=source_sha256,
            purpose=REAL_PURPOSE,
            contract=12,
            input_fn=lambda prompt: (prompts.append(prompt), next(answers))[1],
            output_fn=lambda _message: None,
            stop_after_relationship=True,
        )
    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        contract=12,
        input_fn=lambda prompt: (prompts.append(prompt), next(answers))[1],
        output_fn=lambda _message: None,
        stop_after_relationship=True,
    )

    assert projection["elements"][0]["region"] == [10, 10, 100, 100]
    assert projection["elements"][1]["region"] == [50, 50, 200, 200]
    assert projection["relationships"][0]["from_id"] == "element-000001"
    assert projection["relationships"][0]["to_id"] == "element-000002"
    assert projection["relationships"][0]["binding_method"] == (
        "required_identity_and_selected_identity_containment"
    )
    entries = [
        json.loads(line)
        for line in (attempt / "interview.jsonl").read_text().splitlines()
    ]
    activation = next(
        entry for entry in entries
        if entry["event"] == "overlap_identity_selection_enabled"
    )
    selection = next(
        entry for entry in entries
        if entry["event"] == "answer_recorded"
        and entry["question_id"] == "relationship_binding_resolution"
    )
    assert activation["sequence"] < selection["sequence"]
    selection_prompt = next(
        prompt for prompt in prompts
        if "Which listed recorded element is the exact visible participant" in prompt
    )
    assert "Exact overlapping recorded element choices:" in selection_prompt
    assert '"id": "element-000001"' in selection_prompt
    assert '"id": "element-000002"' in selection_prompt
    assert not any(
        entry["event"] == "element_spatial_identity_refined"
        for entry in entries
    )


def test_coordinate_binding_selects_identities_with_identical_complete_bounds() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["overlap_identity_selection_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["elements"] = [
        {
            "id": "element-000001", "kind": "directional arrow",
            "region": [100, 100, 200, 200], "status": "readable",
            "content": "Visible arrow", "gap_reason": "",
        },
        {
            "id": "element-000002", "kind": "dashboard metric",
            "region": [100, 100, 200, 200], "status": "readable",
            "content": "Visible metric", "gap_reason": "",
        },
    ]
    state["relationship_obligations"] = [{
        "id": "obligation-000001", "element_id": "element-000001",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    state["stage"] = "relationship_binding_resolution"
    state["current"] = {
        "kind": "arrow links to metric",
        "origin_x": 150,
        "origin_y": 150,
        "origin_point": [150, 150],
        "binding_issue": {
            "participant": "origin",
            "point": [150, 150],
            "matching_element_ids": ["element-000001", "element-000002"],
            "reason": "no_unique_recorded_element",
        },
    }

    PROJECTION_INTERVIEW._advance(
        state, "relationship_binding_resolution", "select_recorded_element",
        contract=12,
    )
    question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    parsed, error = PROJECTION_INTERVIEW._parse(
        question, "element-999999", state,
    )
    assert parsed is None
    assert error == (
        "relationship_binding_intended_element: choose one of: "
        "element-000001, element-000002"
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_binding_intended_element", "element-000001",
        contract=12,
    )
    state["current"]["target_x"] = 150
    PROJECTION_INTERVIEW._bind_relationship_point(
        state, "target", 150, contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_binding_resolution", "select_recorded_element",
        contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_binding_intended_element", "element-000002",
        contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_visual_verdict", "supported", contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_status", "readable", contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_description", "The arrow points to the metric.",
        contract=12,
    )

    assert [item["region"] for item in state["elements"]] == [
        [100, 100, 200, 200], [100, 100, 200, 200],
    ]
    assert state["relationships"][0]["from_id"] == "element-000001"
    assert state["relationships"][0]["to_id"] == "element-000002"
    assert state["relationship_obligations"][0]["resolution"] == "relationship"


def test_spatial_identity_choice_requires_append_only_capability_activation() -> None:
    for contract in (12, PROJECTION_INTERVIEW.CONTRACT):
        state = PROJECTION_INTERVIEW._initial_state(contract=contract)
        state["stage"] = "relationship_binding_resolution"
        state["current"] = {
            "binding_issue": {
                "participant": "origin",
                "point": [75, 75],
                "matching_element_ids": ["element-000001", "element-000002"],
                "reason": "no_unique_recorded_element",
            },
        }

        historical = PROJECTION_INTERVIEW._question(
            state,
            purpose=REAL_PURPOSE,
            contract=contract,
        )
        assert historical["choices"] == [
            "retry_coordinates", "record_visible_endpoint", "record_endpoint_gap",
        ]

        state["spatial_identity_refinement_enabled"] = True
        activated = PROJECTION_INTERVIEW._question(
            state,
            purpose=REAL_PURPOSE,
            contract=contract,
        )
        assert activated["choices"] == [
            "retry_coordinates", "record_visible_endpoint",
            "refine_spatial_identity", "record_endpoint_gap",
        ]

        state["overlap_identity_selection_enabled"] = True
        selected = PROJECTION_INTERVIEW._question(
            state,
            purpose=REAL_PURPOSE,
            contract=contract,
        )
        assert selected["choices"] == [
            "retry_coordinates", "record_visible_endpoint",
            "select_recorded_element", "record_endpoint_gap",
        ]


def test_relationship_prompt_identifies_required_element_from_preserved_evidence() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "obligation_resolution"
    state["elements"] = [{
        "id": "element-000008",
        "kind": "dashboard metric",
        "region": [424, 233, 533, 250],
        "status": "readable",
        "content": "250 non-package (69%)",
        "gap_reason": "",
        "capture_scope": "region-r01-c02",
        "scan_region_id": "region-r01-c02",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000008",
        "element_id": "element-000008",
        "status": "pending",
        "resolution": None,
        "relationship_id": None,
    }]

    question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    prompt = PROJECTION_INTERVIEW._prompt(question, state)

    assert '"id": "element-000008"' in prompt
    assert '"kind": "dashboard metric"' in prompt
    assert '"normalized_bounds": [424, 233, 533, 250]' in prompt
    assert '"content": "250 non-package (69%)"' in prompt
    assert '"status": "readable"' in prompt
    assert "Required relationship for element:" not in prompt


def test_terminal_relationship_prompt_lists_every_recorded_outcome_and_obligation() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=13)
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "relationship_more"
    state["elements"] = [
        {
            "id": "element-000001", "kind": "annotation", "region": [10, 10, 90, 90],
            "status": "readable", "content": "Column AC", "gap_reason": "",
        },
        {
            "id": "element-000002", "kind": "metric", "region": [100, 10, 180, 90],
            "status": "readable", "content": "64 codes", "gap_reason": "",
        },
    ]
    state["relationships"] = [
        {
            "id": "relationship-000001", "kind": "arrow-points-to",
            "from_id": "element-000001", "to_id": "element-000002",
            "status": "readable", "description": "Column AC points to 64 codes.",
            "gap_reason": "",
        },
        {
            "id": "relationship-000002", "kind": "annotation arrow",
            "from_id": None, "to_id": "element-000002", "status": "gap",
            "description": "", "gap_reason": "The origin could not be bound.",
            "origin_point": [750, 405], "target_point": [625, 370],
            "binding_issue": {
                "participant": "origin", "point": [750, 405],
                "matching_element_ids": [], "reason": "no_unique_recorded_element",
            },
        },
    ]
    state["relationship_obligations"] = [
        {"id": "obligation-000001", "status": "resolved"},
        {"id": "obligation-000002", "status": "resolved"},
    ]
    question = PROJECTION_INTERVIEW._field(
        "relationship_more",
        "Is there another purpose-relevant visible relationship that has not been recorded?",
        "choice",
        choices=["yes", "no"],
    )

    prompt = PROJECTION_INTERVIEW._prompt(question, state)

    context_text = prompt.split(
        "Complete code-generated recorded-relationship index: ", 1,
    )[1].split("\n", 1)[0]
    context = json.loads(context_text)
    assert context["recorded_relationship_count"] == 2
    assert [
        item["relationship_id"] for item in context["recorded_relationships"]
    ] == ["relationship-000001", "relationship-000002"]
    assert context["recorded_relationships"][1]["participants"][0] == {
        "role": "origin", "element_id": None, "status": "unbound",
        "normalized_point": [750, 405],
        "binding_issue": state["relationships"][1]["binding_issue"],
    }
    assert context["resolved_relationship_obligation_count"] == 2
    assert context["pending_relationship_obligation_count"] == 0


def test_relationship_endpoint_capture_prompt_distinguishes_other_participant() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "element_content"
    state["elements"] = [{
        "id": "element-000027", "kind": "annotation", "region": [312, 265, 413, 308],
        "status": "readable", "content": "Sum of Column X divided by Column W",
        "gap_reason": "", "capture_scope": "region-r02-c02",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000027", "element_id": "element-000027",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    state["current"] = {
        "capture_scope": "relationship_endpoint",
        "return_stage": "relationship_target_x",
        "kind": "metric", "left": 355, "top": 318, "right": 425,
        "bottom": 365, "status": "readable",
    }

    question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    prompt = PROJECTION_INTERVIEW._prompt(question, state)

    assert "record the other visible endpoint" in prompt
    assert "Do not copy or recapture the already-recorded participant" in prompt
    assert "Select one precise visible endpoint" in prompt
    assert "collect a separate context window" in prompt


def test_region_prompt_does_not_receive_pending_relationship_evidence() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["elements"] = [{
        "id": "element-000001",
        "kind": "annotation callout",
        "region": [10, 10, 100, 100],
        "status": "readable",
        "content": "Visible description",
        "gap_reason": "",
        "capture_scope": "region-r01-c01",
        "scan_region_id": "region-r01-c01",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000001",
        "element_id": "element-000001",
        "status": "pending",
        "resolution": None,
        "relationship_id": None,
    }]
    question = PROJECTION_INTERVIEW._field(
        "region_element_more", "Another element?", "choice",
        choices=["yes", "no"],
    )

    prompt = PROJECTION_INTERVIEW._prompt(question, state)

    assert "Required relationship element evidence:" not in prompt


def test_relationship_reuse_decision_receives_complete_ordered_element_index() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "obligation_resolution"
    state["elements"] = [
        {
            "id": "element-000011",
            "kind": "annotation callout",
            "region": [511, 1, 709, 49],
            "status": "readable",
            "content": "Clicking refresh updates the displayed numbers.",
            "gap_reason": "",
            "capture_scope": "region-r01-c03",
            "scan_region_id": "region-r01-c03",
        },
        {
            "id": "element-000057",
            "kind": "button",
            "region": [460, 64, 530, 92],
            "status": "readable",
            "content": "Refresh",
            "gap_reason": "",
            "capture_scope": "relationship_endpoint",
        },
        {
            "id": "element-000012",
            "kind": "directional arrow",
            "region": [528, 48, 568, 66],
            "status": "gap",
            "content": "",
            "gap_reason": "Arrow endpoint is visually unclear.",
            "capture_scope": "region-r01-c03",
            "scan_region_id": "region-r01-c03",
        },
    ]
    state["relationship_obligations"] = [{
        "id": "obligation-000011",
        "element_id": "element-000011",
        "status": "pending",
        "resolution": None,
        "relationship_id": None,
    }]

    prompt = PROJECTION_INTERVIEW._prompt(
        PROJECTION_INTERVIEW._question(
            state, purpose=REAL_PURPOSE, contract=12,
        ),
        state,
    )

    index = prompt.split(
        "Complete index of other recorded relationship endpoint candidates: ", 1,
    )[1].split("\n", 1)[0]
    candidates = json.loads(index)
    assert [item["id"] for item in candidates] == [
        "element-000012", "element-000057",
    ]
    assert candidates[0]["gap_reason"] == "Arrow endpoint is visually unclear."
    assert candidates[1] == {
        "content": "Refresh",
        "gap_reason": "",
        "id": "element-000057",
        "kind": "button",
        "normalized_bounds": [460, 64, 530, 92],
        "status": "readable",
    }
    assert "element-000011" not in index


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
        contract=7,
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
        contract=7,
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
        contract=7,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    relationship = projection["relationships"][0]
    assert relationship["status"] == "gap"
    assert relationship["visual_verification"] == "unreadable"
    assert relationship["gap_reason"] == (
        "The connector passes behind an opaque overlay."
    )


def test_supported_pair_resolves_both_participant_obligations_but_not_unrelated(
    tmp_path: Path,
) -> None:
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation", "10", "10", "100", "100", "readable",
        "Formula description", "yes",
        "yes", "dashboard field", "120", "10", "220", "100", "readable",
        "Conversion rate", "yes",
        "yes", "unrelated annotation", "10", "120", "100", "200", "readable",
        "A separate description", "yes",
        "no", *(["no"] * 15),
        "use_recorded_endpoint", "visible connector",
        "10", "10", "120", "10", "supported", "readable",
        "The annotation applies to the field.",
    ])

    projection = PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="9" * 64,
        purpose=REAL_PURPOSE,
        contract=7,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
        stop_after_relationship=True,
    )

    assert [
        (item["status"], item["relationship_id"])
        for item in projection["relationship_obligations"]
    ] == [
        ("resolved", "relationship-000001"),
        ("resolved", "relationship-000001"),
        ("pending", None),
    ]
    assert [item["verified_obligation_id"] for item in projection["relationships"]] == [
        "obligation-000001",
    ]
    entries = [
        json.loads(line)
        for line in (tmp_path / "attempt" / "interview.jsonl").read_text().splitlines()
    ]
    reconciliation = [
        entry
        for entry in entries
        if entry["event"] == "relationship_obligations_reconciled"
    ]
    assert [{
        "obligation_id": "obligation-000002",
        "element_id": "element-000002",
    }] == reconciliation[0]["covered_obligations"]
    assert reconciliation[0]["relationship_id"] == "relationship-000001"


def test_visual_verdict_is_code_constrained_to_three_values(tmp_path: Path) -> None:
    answers = _projection_answers()
    verdict_index = answers.index("supported")
    answers.insert(verdict_index, "maybe")
    messages: list[str] = []

    PROJECTION_INTERVIEW.run(
        tmp_path / "attempt",
        source_sha256="a" * 64,
        purpose=REAL_PURPOSE,
        contract=7,
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
        contract=7,
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


def test_projection_interview_can_record_an_optional_relationship_after_all_obligations(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "optional-relationship-attempt"
    answers = _projection_answers(contract=6)
    assert answers[-1] == "no"
    answers[-1:] = [
        "yes",
        "additional-visible-link",
        "10", "20", "120", "20",
        "supported",
        "readable",
        "The first recorded element also has a second visible link to the target.",
        "no",
    ]

    created = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256="8" * 64,
        purpose=REAL_PURPOSE,
        contract=6,
        input_fn=lambda _prompt: answers.pop(0),
        output_fn=lambda _message: None,
    )
    replayed, _, _ = PROJECTION_INTERVIEW.validate(
        attempt,
        source_sha256="8" * 64,
        purpose=REAL_PURPOSE,
        contract=6,
    )

    assert replayed == created
    assert [item["kind"] for item in created["relationships"]] == [
        "visually-connected-to",
        "additional-visible-link",
    ]
    assert created["relationships"][1]["visual_verification"] == "supported"
    assert "verified_obligation_id" not in created["relationships"][1]


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
        str(
            (
                work
                / "projection-interviews"
                / "attempt-000001"
                / "region-evidence"
                / "region-r01-c01.png"
            ).resolve()
        ),
        str(
            (
                work
                / "projection-interviews"
                / "attempt-000001"
                / "region-evidence"
                / "region-r01-c01.ownership.png"
            ).resolve()
        ),
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


def test_projection_request_binds_one_immutable_crop_and_advances_one_region(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "grid.png"
    image = Image.new("RGB", (40, 40), "white")
    for row in range(4):
        for column in range(4):
            color = (row * 50, column * 50, (row + column) * 25)
            for y in range(row * 10, (row + 1) * 10):
                for x in range(column * 10, (column + 1) * 10):
                    image.putpixel((x, y), color)
    image.save(supplied, format="PNG")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)

    first = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    first_crop = Path(first["work"][0]["attachments"][0])
    first_guide = Path(first["work"][0]["attachments"][1])
    first_entries = [
        json.loads(line)
        for line in (
            work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
        ).read_text().splitlines()
    ]

    assert first_crop.name == "region-r01-c01.png"
    assert Image.open(first_crop).size == (12, 12)
    first_region_event = next(
        entry for entry in first_entries
        if entry["event"] == "region_evidence_bound"
    )
    assert first_region_event["region_id"] == "region-r01-c01"
    assert first_region_event["core_normalized_bounds"] == [0, 0, 250, 250]
    assert first_region_event["evidence_normalized_bounds"] == [0, 0, 300, 300]
    assert first_region_event["core_pixel_bounds"] == [0, 0, 10, 10]
    assert first_region_event["pixel_bounds"] == [0, 0, 12, 12]
    assert first_region_event["ownership_core_in_crop_pixels"] == [0, 0, 10, 10]
    assert first_region_event["guide_path"] == (
        "region-evidence/region-r01-c01.ownership.png"
    )
    assert first_region_event["guide_sha256"] == START_INTAKE._digest_bytes(
        first_guide.read_bytes()
    )
    assert first_region_event["crop_sha256"] == START_INTAKE._digest_bytes(
        first_crop.read_bytes()
    )

    answers = iter(["test-model", "pytest", "no"])
    second = START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
        single_region=True,
    )
    second_crop = Path(second["work"][0]["attachments"][0])
    entries = [
        json.loads(line)
        for line in (
            work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
        ).read_text().splitlines()
    ]

    assert second["stopped"] == "interviewing_first_projection"
    assert second_crop.name == "region-r01-c02.png"
    assert Image.open(second_crop).size == (12, 12)
    assert [entry["event"] for entry in entries].count("region_outcome_recorded") == 1
    outcome = next(
        entry for entry in entries if entry["event"] == "region_outcome_recorded"
    )
    assert outcome["region_id"] == "region-r01-c01"
    assert outcome["status"] == "scanned"
    assert outcome["crop_sha256"] == first_region_event["crop_sha256"]


def test_projection_defers_context_only_candidate_without_element_or_obligation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    attachments = PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    answers = iter([
        "test-model", "pytest", "yes", "context callout", "context_only",
        "260", "10", "no",
    ])
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        input_fn=answer,
        output_fn=lambda _message: None,
    )
    next_attachments = PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    entries = [
        json.loads(line)
        for line in (attempt / "interview.jsonl").read_text().splitlines()
    ]
    deferral = next(
        entry for entry in entries if entry["event"] == "context_candidate_deferred"
    )

    assert PROJECTION_INTERVIEW.CONTRACT == 13
    assert isinstance(attachments, tuple)
    crop, guide = attachments
    assert crop.name == "region-r01-c01.png"
    assert guide.name == "region-r01-c01.ownership.png"
    assert Image.open(crop).size == Image.open(guide).size == (12, 12)
    assert any(
        "owned_by_active_core" in prompt and "context_only" in prompt
        for prompt in prompts
    )
    assert projection["elements"] == []
    assert projection["relationship_obligations"] == []
    assert isinstance(next_attachments, tuple)
    assert next_attachments[0].name == "region-r01-c02.png"
    assert deferral["region_id"] == "region-r01-c01"
    assert deferral["owner_region_id"] == "region-r01-c02"
    assert deferral["obligation_id"] == "context-obligation-000001"
    assert deferral["anchor"] == [260, 10]
    assert deferral["candidate_kind"] == "context callout"
    assert deferral["crop_sha256"] == entries[0]["crop_sha256"]
    assert deferral["guide_sha256"] == entries[0]["guide_sha256"]
    assert projection["scan_regions"][0]["deferred_context_candidates"] == [
        {
            "candidate_kind": "context callout",
            "obligation_id": "context-obligation-000001",
            "owner_region_id": "region-r01-c02",
            "anchor": [260, 10],
            "crop_sha256": deferral["crop_sha256"],
            "guide_sha256": deferral["guide_sha256"],
            "reason": "context_only",
        }
    ]
    assert projection["scan_regions"][1]["context_candidate_obligations"] == [
        {
            "id": "context-obligation-000001",
            "source_region_id": "region-r01-c01",
            "candidate_kind": "context callout",
            "anchor": [260, 10],
            "status": "pending",
            "resolution": None,
            "element_id": None,
            "gap_reason": "",
        }
    ]


def test_projection_does_not_offer_context_only_without_visible_context() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=13)
    state["scan_region_index"] = 15
    region = PROJECTION_INTERVIEW._active_scan_region(state)
    assert region is not None
    region["evidence"] = {
        "core_normalized_bounds": [750, 750, 1000, 1000],
        "evidence_normalized_bounds": [750, 750, 1000, 1000],
    }
    state["stage"] = "element_ownership"
    state["current"] = {
        "kind": "visible element",
        "scan_region_id": region["id"],
    }

    question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=13,
    )

    assert question is not None
    assert question["choices"] == ["owned_by_active_core"]
    assert "no surrounding context" in str(question["prompt"])


def test_projection_replays_contract12_ownership_question_after_contract13_narrowing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=13)
    state["scan_region_index"] = 15
    region = PROJECTION_INTERVIEW._active_scan_region(state)
    assert region is not None
    region["evidence"] = {
        "core_normalized_bounds": [750, 750, 1000, 1000],
        "evidence_normalized_bounds": [750, 750, 1000, 1000],
    }
    state["stage"] = "element_ownership"
    state["current"] = {
        "kind": "description annotation box",
        "scan_region_id": region["id"],
    }
    legacy_question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    monkeypatch.setattr(
        PROJECTION_INTERVIEW,
        "_initial_state",
        lambda *, contract: state,
    )

    replayed, pending, completed = PROJECTION_INTERVIEW._replay(
        [
            {
                "event": "question_asked",
                "question": legacy_question,
                "sequence": 1317,
            },
            {
                "event": "answer_recorded",
                "question_id": "element_ownership",
                "raw": "context_only",
                "parsed": "context_only",
                "accepted": True,
                "error": None,
                "sequence": 1318,
            },
        ],
        purpose=REAL_PURPOSE,
        contract=13,
    )

    assert replayed["stage"] == "context_anchor_x"
    assert pending is None
    assert completed is False


def test_projection_replays_supported_older_feature_activation_contract() -> None:
    state, pending, completed = PROJECTION_INTERVIEW._replay(
        [
            {
                "event": "spatial_identity_refinement_enabled",
                "feature": "append_only_spatial_identity_refinement_v1",
                "contract": 12,
                "sequence": 1677,
            },
        ],
        purpose=REAL_PURPOSE,
        contract=13,
    )

    assert state["spatial_identity_refinement_enabled"] is True
    assert pending is None
    assert completed is False


def test_projection_reclassifies_preserved_impossible_context_answer() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["scan_region_index"] = 15
    region = PROJECTION_INTERVIEW._active_scan_region(state)
    assert region is not None
    region["evidence"] = {
        "core_normalized_bounds": [750, 750, 1000, 1000],
        "evidence_normalized_bounds": [750, 750, 1000, 1000],
        "crop_sha256": "a" * 64,
        "guide_sha256": "b" * 64,
    }
    state["stage"] = "context_anchor_y"
    state["current"] = {
        "kind": "visible element",
        "scan_region_id": region["id"],
        "context_anchor_x": 750,
    }
    pending = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )

    event = PROJECTION_INTERVIEW._context_ownership_reclassification(
        state, pending, contract=12,
    )

    assert event is not None
    assert event["cancelled_question_id"] == "context_anchor_y"
    assert event["classification"] == "owned_by_active_core"
    PROJECTION_INTERVIEW._apply_context_ownership_reclassification(state, event)
    assert state["stage"] == "element_left"
    assert "context_anchor_x" not in state["current"]


def test_projection_context_cannot_claim_an_element_outside_ownership_core(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    attachments = PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    answers = iter([
        "test-model", "pytest", "yes", "value", "owned_by_active_core",
        "260", "10", "10", "290", "100", "readable", "$8,100", "no", "no",
    ])
    prompts: list[str] = []
    messages: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        input_fn=answer,
        output_fn=messages.append,
    )

    assert isinstance(attachments, tuple)
    crop, _guide = attachments
    assert Image.open(crop).size == (12, 12)
    assert any("crop edges map to [0, 0, 300, 300]" in item for item in prompts)
    assert any("bright green outline" in item for item in prompts)
    assert any("normalized bounds [0, 0, 250, 250]" in item for item in prompts)
    assert messages == [
        (
            "Invalid answer: element_left: left coordinate 260 must be inside "
            "active region-r01-c01 horizontal bounds 0 through 249."
        )
    ]
    assert projection["elements"][0]["region"] == [10, 10, 290, 100]
    assert projection["elements"][0]["scan_region_id"] == "region-r01-c01"


def test_projection_owner_region_requires_context_deferral_outcome(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    first_answers = iter([
        "test-model", "pytest", "yes", "context callout", "context_only",
        "260", "10", "no",
    ])
    PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(first_answers),
        output_fn=lambda _message: None,
    )
    PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    second_answers = iter([
        "record_explicit_gap", "candidate is unreadable in its owning crop", "no",
    ])
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(second_answers)

    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        input_fn=answer,
        output_fn=lambda _message: None,
    )
    obligation = projection["scan_regions"][1][
        "context_candidate_obligations"
    ][0]

    assert any(
        "record_owned_element" in prompt and "record_explicit_gap" in prompt
        for prompt in prompts
    )
    assert obligation["status"] == "resolved"
    assert obligation["resolution"] == "gap"
    assert obligation["element_id"] == "element-000001"
    assert obligation["gap_reason"] == (
        "candidate is unreadable in its owning crop"
    )
    assert projection["scan_regions"][1]["status"] == "scanned"
    assert projection["scan_regions"][1]["element_ids"] == [
        "element-000001"
    ]
    assert projection["elements"] == [
        {
            "id": "element-000001",
            "kind": "context callout",
            "region": [260, 10, 261, 11],
            "status": "gap",
            "content": "",
            "gap_reason": "candidate is unreadable in its owning crop",
            "capture_scope": "region-r01-c02",
            "scan_region_id": "region-r01-c02",
        }
    ]
    selected_gaps = START_INTAKE.gap_clarification.select_gaps(
        projection, "a" * 64,
    )
    assert [(item["collection"], item["id"]) for item in selected_gaps] == [
        ("elements", "element-000001")
    ]


def test_projection_owner_region_records_deferred_candidate_as_one_element(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    first_answers = iter([
        "test-model", "pytest", "yes", "context callout", "context_only",
        "260", "10", "no",
    ])
    PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(first_answers),
        output_fn=lambda _message: None,
    )
    PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    second_answers = iter([
        "record_owned_element",
        "250", "0", "255", "300", "50",
        "readable", "Column AC", "no", "no",
    ])
    messages: list[str] = []
    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(second_answers),
        output_fn=messages.append,
    )
    obligation = projection["scan_regions"][1][
        "context_candidate_obligations"
    ][0]

    assert messages == [
        (
            "Invalid answer: element_right: value 255 does not contain deferred "
            "candidate anchor [260, 10]; enter a value greater than 260."
        )
    ]
    assert obligation["status"] == "resolved"
    assert obligation["resolution"] == "element"
    assert obligation["element_id"] == "element-000001"
    assert obligation["gap_reason"] == ""
    assert projection["elements"] == [
        {
            "id": "element-000001",
            "kind": "context callout",
            "region": [250, 0, 300, 50],
            "status": "readable",
            "content": "Column AC",
            "gap_reason": "",
            "capture_scope": "region-r01-c02",
            "scan_region_id": "region-r01-c02",
        }
    ]


def test_projection_same_unit_merge_resolves_deferred_context_obligation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    first_answers = iter([
        "test-model", "pytest",
        "yes", "metric", "owned_by_active_core",
        "240", "0", "300", "50", "readable", "114 package (31%)", "no",
        "yes", "button", "context_only", "260", "10",
        "no",
    ])
    PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(first_answers),
        output_fn=lambda _message: None,
    )
    PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    second_answers = iter([
        "record_owned_element",
        "250", "0", "300", "50",
        "same_unit", "element-000001",
        "240", "0", "300", "50", "readable", "114 package (31%)",
        "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(second_answers),
        output_fn=lambda _message: None,
    )

    obligation = projection["scan_regions"][1][
        "context_candidate_obligations"
    ][0]
    assert obligation == {
        "id": "context-obligation-000001",
        "source_region_id": "region-r01-c01",
        "candidate_kind": "button",
        "anchor": [260, 10],
        "status": "resolved",
        "resolution": "element",
        "element_id": "element-000001",
        "gap_reason": "",
    }
    entries = [
        json.loads(line)
        for line in (attempt / "interview.jsonl").read_text().splitlines()
    ]
    supersession = next(
        entry
        for entry in entries
        if entry.get("event") == "element_superseded"
        and "context_obligation_resolution" in entry
    )
    assert supersession["context_obligation_resolution"]["obligation_id"] == (
        "context-obligation-000001"
    )


def test_projection_rejects_rehashed_context_owner_tamper(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    answers = iter([
        "test-model", "pytest", "yes", "context callout", "context_only",
        "260", "10", "no",
    ])
    PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    journal = attempt / "interview.jsonl"
    entries = [json.loads(line) for line in journal.read_text().splitlines()]
    deferral = next(
        entry for entry in entries
        if entry["event"] == "context_candidate_deferred"
    )
    deferral["owner_region_id"] = "region-r01-c03"
    previous: str | None = None
    rewritten: list[dict[str, object]] = []
    for sequence, entry in enumerate(entries, start=1):
        payload = {
            key: value for key, value in entry.items()
            if key not in {
                "sequence", "event", "previous_entry_sha256", "entry_sha256",
            }
        }
        rebuilt = PROJECTION_INTERVIEW._entry(
            sequence, entry["event"], payload, previous,
        )
        previous = rebuilt["entry_sha256"]
        rewritten.append(rebuilt)
    journal.write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in rewritten)
    )

    with pytest.raises(
        PROJECTION_INTERVIEW.InterviewError,
        match="context-deferral-invalid",
    ):
        PROJECTION_INTERVIEW.prepare_region_evidence(
            attempt,
            source_path=source,
            source_sha256=source_sha256,
            purpose=REAL_PURPOSE,
        )


def test_projection_supersedes_a_contained_fragment_without_duplicate_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    answers = iter([
        "test-model", "pytest",
        "yes", "annotation callout", "owned_by_active_core",
        "43", "89", "125", "121",
        "readable", "Column: W", "yes",
        "yes", "annotation text", "owned_by_active_core",
        "56", "105", "111", "113",
        "same_unit", "element-000001",
        "50", "43", "89", "125", "121", "readable",
        "Column: W; % = 300/364", "no",
    ])
    prompts: list[str] = []
    messages: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        input_fn=answer,
        output_fn=messages.append,
    )
    next_attachments = PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    entries = [
        json.loads(line)
        for line in (attempt / "interview.jsonl").read_text().splitlines()
    ]
    supersession = next(
        entry for entry in entries if entry["event"] == "element_superseded"
    )

    assert PROJECTION_INTERVIEW.CONTRACT == 13
    assert any("same_unit" in prompt and "element-000001" in prompt for prompt in prompts)
    assert messages == [
        "Invalid answer: element_merge_left: enter a value from 0 through 43."
    ]
    assert isinstance(next_attachments, tuple)
    next_crop, _next_guide = next_attachments
    assert next_crop.name == "region-r01-c02.png"
    assert len(projection["elements"]) == 1
    assert projection["elements"][0]["id"] == "element-000001"
    assert projection["elements"][0]["region"] == [43, 89, 125, 121]
    assert projection["elements"][0]["content"] == "Column: W; % = 300/364"
    assert [item["element_id"] for item in projection["relationship_obligations"]] == [
        "element-000001"
    ]
    assert supersession["element_id"] == "element-000001"
    assert supersession["previous_element"]["content"] == "Column: W"
    assert supersession["replacement_element"] == projection["elements"][0]
    assert supersession["trigger_candidate"]["region"] == [56, 105, 111, 113]


def test_relationship_endpoint_supersession_restores_the_captured_relationship_draft() -> None:
    state = PROJECTION_INTERVIEW._initial_state(
        contract=PROJECTION_INTERVIEW.CONTRACT,
    )
    origin = {
        "id": "element-000001",
        "kind": "annotation callout linked to a dashboard metric value",
        "region": [32, 44, 186, 139],
        "status": "readable",
        "content": "Column:AF points to $8,100",
        "gap_reason": "",
        "capture_scope": "region-r01-c01",
        "scan_region_id": "region-r01-c01",
    }
    previous_target = {
        "id": "element-000053",
        "kind": "metric value",
        "region": [194, 120, 268, 151],
        "status": "readable",
        "content": "NET REVENUE TODAY displays $8,100",
        "gap_reason": "",
        "capture_scope": "relationship_endpoint",
    }
    replacement_target = {
        **previous_target,
        "region": [184, 98, 571, 175],
        "content": "NET REVENUE TODAY displays $8,100 and Operator Net",
    }
    event = {
        "element_id": "element-000053",
        "reason": "same_visible_unit",
        "previous_element": previous_target,
        "trigger_candidate": {
            "kind": "dashboard metric card",
            "region": [184, 98, 571, 175],
        },
        "replacement_element": replacement_target,
    }
    state["elements"] = [origin, previous_target]
    state["relationship_obligations"] = [{
        "id": "obligation-000001",
        "element_id": "element-000001",
        "status": "pending",
        "resolution": None,
        "relationship_id": None,
    }]
    state["relationship_draft"] = {
        "kind": "annotation callout arrow linking a data-source label to a dashboard metric value",
        "origin_x": 100,
        "origin_y": 65,
        "origin_id": "element-000001",
        "origin_point": [100, 65],
    }
    state["element_supersession_pending"] = {
        "event": event,
        "return_stage": "relationship_target_x",
    }

    PROJECTION_INTERVIEW._apply_element_supersession(state, event)
    PROJECTION_INTERVIEW._advance(
        state, "relationship_target_x", 300,
        contract=PROJECTION_INTERVIEW.CONTRACT,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_target_y", 105,
        contract=PROJECTION_INTERVIEW.CONTRACT,
    )

    assert state["current"]["origin_id"] == "element-000001"
    assert state["current"]["target_id"] == "element-000053"
    assert state["stage"] == "relationship_visual_verdict"


def test_projection_keeps_spatially_nested_distinct_units_separate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
    )
    answers = iter([
        "test-model", "pytest",
        "yes", "container", "owned_by_active_core",
        "10", "10", "200", "200",
        "readable", "Outer", "no",
        "yes", "nested value", "owned_by_active_core",
        "50", "50", "100", "100",
        "distinct_unit", "readable", "Inner", "no", "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    events = [
        json.loads(line)["event"]
        for line in (attempt / "interview.jsonl").read_text().splitlines()
    ]

    assert [item["content"] for item in projection["elements"]] == [
        "Outer", "Inner"
    ]
    assert "element_superseded" not in events


def test_projection_contract_nine_replays_without_unit_collision_gate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    crop = PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        contract=9,
    )
    answers = iter([
        "test-model", "pytest",
        "yes", "container", "10", "10", "200", "200",
        "readable", "Outer", "no",
        "yes", "nested value", "50", "50", "100", "100",
        "readable", "Inner", "no", "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        contract=9,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    assert crop is not None
    assert Image.open(crop).size == (12, 12)
    assert projection["schema_version"] == 9
    assert [item["content"] for item in projection["elements"]] == [
        "Outer", "Inner"
    ]


def test_projection_contract_ten_replays_without_ownership_admission_gate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    crop = PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        contract=10,
    )
    answers = iter([
        "test-model", "pytest",
        "yes", "container", "10", "10", "200", "200",
        "readable", "Outer", "no",
        "yes", "nested value", "50", "50", "100", "100",
        "distinct_unit", "readable", "Inner", "no", "no",
    ])

    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        contract=10,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    assert isinstance(crop, Path)
    assert crop.name == "region-r01-c01.png"
    assert projection["schema_version"] == 10
    assert [item["content"] for item in projection["elements"]] == [
        "Outer", "Inner"
    ]


def test_projection_contract_eleven_replays_without_context_owner_routing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    attachments = PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        contract=11,
    )
    answers = iter([
        "test-model", "pytest", "yes", "context callout", "context_only", "no",
    ])
    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        contract=11,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    next_attachments = PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        contract=11,
    )

    assert isinstance(attachments, tuple)
    assert isinstance(next_attachments, tuple)
    assert Image.open(next_attachments[0]).size == (14, 12)
    assert projection["schema_version"] == 11
    assert "context_candidate_obligations" not in projection["scan_regions"][1]
    assert projection["scan_regions"][0]["deferred_context_candidates"] == [
        {
            "candidate_kind": "context callout",
            "reason": "context_only",
            "crop_sha256": projection["scan_regions"][0]["evidence"][
                "crop_sha256"
            ],
            "guide_sha256": projection["scan_regions"][0]["evidence"][
                "guide_sha256"
            ],
        }
    ]


def test_projection_contract_eight_keeps_exact_crop_replayable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    attempt = tmp_path / "attempt"
    source_sha256 = START_INTAKE._digest_bytes(source.read_bytes())
    crop = PROJECTION_INTERVIEW.prepare_region_evidence(
        attempt,
        source_path=source,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        contract=8,
    )
    answers = iter(["test-model", "pytest", "no"])

    projection = PROJECTION_INTERVIEW.run(
        attempt,
        source_sha256=source_sha256,
        purpose=REAL_PURPOSE,
        contract=8,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    event = json.loads((attempt / "interview.jsonl").read_text().splitlines()[0])

    assert crop is not None
    assert Image.open(crop).size == (10, 10)
    assert event["normalized_bounds"] == [0, 0, 250, 250]
    assert event["pixel_bounds"] == [0, 0, 10, 10]
    assert event["adapter"] == PROJECTION_INTERVIEW.REGION_EVIDENCE_ADAPTER_V1
    assert projection["schema_version"] == 8


def test_projection_region_crop_cannot_be_overwritten(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "source.png")
    waiting = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    crop = Path(waiting["work"][0]["attachments"][0])
    crop.write_bytes(b"changed")

    blocked = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)

    assert blocked["status"] == "blocked"
    assert blocked["stopped"] == "projection region evidence failed"
    assert "region-evidence-changed:region-r01-c01" in blocked["why"]


def test_projection_region_ownership_guide_cannot_be_overwritten(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "source.png")
    waiting = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    guide = Path(waiting["work"][0]["attachments"][1])
    guide.write_bytes(b"changed")

    blocked = START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)

    assert blocked["status"] == "blocked"
    assert blocked["stopped"] == "projection region evidence failed"
    assert "region-ownership-guide-changed:region-r01-c01" in blocked["why"]


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
    answers = iter(_projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT))

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
    assert accepted["projection"]["element_count"] == 3
    assert accepted["projection"]["relationship_count"] == 1
    assert accepted["projection"]["gap_count"] == 1
    assert before == after
    projection = json.loads((work / accepted["projection"]["path"]).read_text())
    assert projection["reader"] == {"model": "test-model", "harness": "pytest"}
    assert [item["id"] for item in projection["elements"]] == [
            "element-000001", "element-000002", "element-000003"
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
    request_attachments, _command = CODEX_RUNNER.load_request(work)
    assert isinstance(request_attachments, tuple)
    assert request_attachments[0].name == "region-r01-c01.png"

    for page_number, visible_text in enumerate(
        ("Page one description", "Page two note"), start=1
    ):
        answers = _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
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
            page_attachments, _page_command = CODEX_RUNNER.load_request(work)
            assert isinstance(page_attachments, tuple)
            assert page_attachments[0].name == "region-r01-c01.png"
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
        "element-000003",
        "element-000003",
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
        "element-000003",
        "element-000003",
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
    assert waiting["question"]["answers_gap"]["item_id"] == "element-000003"
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
    producer_answers = iter(
        _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
    )
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
    producer_answers = iter(
        _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
    )
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
    assert accepted["projection"]["element_count"] == 4
    assert accepted["projection"]["gap_count"] == 1
    ledger = [json.loads(line) for line in (work / "ledger.jsonl").read_text().splitlines()]
    assert ledger[-2]["correction_result_sha256"]
    assert ledger[-2]["correction_verification_result_sha256"]


def test_invalid_enum_answers_are_preserved_without_entering_projection(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    answers = iter(_projection_answers(
        invalid_status_first=True,
        contract=PROJECTION_INTERVIEW.CONTRACT,
    ))
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
    waiting = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True,
    )
    command = waiting["work"][0]["command"]
    assert command[-3:] == [
        "--projection-region-id", "region-r01-c01", "--run-projection-interview",
    ]

    completed = subprocess.run(
        command,
        input="\n".join(
            _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
        ) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    result = json.loads(completed.stdout)
    assert result["stopped"] == "projection_region_step_complete"
    assert result["completed_region_id"] == "region-r01-c01"
    assert "Allowed values: readable, gap" in completed.stderr
    next_attachment, next_command = CODEX_RUNNER.load_request(work)
    assert isinstance(next_attachment, tuple)
    assert next_attachment[0].name == "region-r01-c02.png"
    assert next_command[-3:] == [
        "--projection-region-id", "region-r01-c02", "--run-projection-interview",
    ]
    journal = [
        json.loads(line)
        for line in (
            work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
        ).read_text().splitlines()
    ]
    assert [
        entry["region_id"]
        for entry in journal
        if entry["event"] == "region_outcome_recorded"
    ] == ["region-r01-c01"]

    reused = subprocess.run(
        command, text=True, capture_output=True, check=False,
    )
    assert reused.returncode == 3
    reused_result = json.loads(reused.stdout)
    assert reused_result["stopped"] == "projection region invocation expired"
    assert "region-r01-c01" in reused_result["why"]


def test_cli_binds_and_stops_after_one_relationship_obligation(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    waiting = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True,
    )
    answers = iter(_projection_answers(
        contract=PROJECTION_INTERVIEW.CONTRACT,
        second_relationship_obligation=True,
        third_relationship_obligation=True,
    ))

    for _ in range(16):
        waiting = START_INTAKE.run_first_projection_interview(
            work,
            input_fn=lambda _prompt: next(answers),
            output_fn=lambda _message: None,
            single_region=True,
        )

    assert waiting["status"] == "waiting_for_model"
    attachment, command = CODEX_RUNNER.load_request(work)
    assert isinstance(attachment, Path)
    assert attachment.name.startswith(
        "element-000001-required-recorded-participant-"
    )
    assert attachment.suffix == ".png"
    assert command[-5] == "--projection-obligation-id"
    assert command[-4] == "obligation-000001"
    assert command[-3] == "--projection-endpoint-evidence-sha256"

    verified = subprocess.run(
        command,
        input=next(answers) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    assert verified.returncode == 2
    verification_result = json.loads(verified.stdout)
    assert verification_result["stopped"] == (
        "projection_endpoint_verification_step_complete"
    )
    attachment, command = CODEX_RUNNER.load_request(work)
    assert isinstance(attachment, Path)
    assert attachment.name == "source-000003"
    assert command[-3:] == [
        "--projection-obligation-id", "obligation-000001",
        "--run-projection-interview",
    ]

    completed = subprocess.run(
        command,
        input="\n".join(list(answers)) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    result = json.loads(completed.stdout)
    assert result["stopped"] == "projection_relationship_step_complete"
    assert result["completed_obligation_id"] == "obligation-000001"
    journal = (
        work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
    )
    assert CODEX_RUNNER._projection_region_outcome_count(journal) == 16
    assert CODEX_RUNNER._projection_relationship_outcome_count(journal) == 1
    assert not journal.with_name("projection.json").exists()

    next_attachment, next_command = CODEX_RUNNER.load_request(work)
    assert isinstance(next_attachment, Path)
    assert next_attachment.name.startswith(
        "element-000004-required-recorded-participant-"
    )
    assert next_attachment.suffix == ".png"
    assert next_command[-5] == "--projection-obligation-id"
    assert next_command[-4] == "obligation-000003"
    assert next_command[-3] == "--projection-endpoint-evidence-sha256"


def test_changed_projection_version_fails_closed(tmp_path: Path) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    answers = iter(_projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT))
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


def test_relationship_gap_question_is_code_grounded_to_recorded_candidates(
    tmp_path: Path,
) -> None:
    relationship = {
        "id": "relationship-000003",
        "kind": "annotation arrow connects",
        "from_id": None,
        "to_id": None,
        "origin_point": [93, 137],
        "status": "gap",
        "description": "",
        "gap_reason": "The origin point matches two recorded elements.",
        "binding_issue": {
            "participant": "origin",
            "matching_element_ids": ["element-000002", "element-000003"],
            "point": [93, 137],
            "reason": "no_unique_recorded_element",
        },
    }
    projection = {
        "elements": [
            {
                "id": "element-000001",
                "kind": "annotation callout",
                "region": [32, 42, 151, 88],
                "status": "readable",
                "content": "Column: AF",
            },
            {
                "id": "element-000002",
                "kind": "annotation callout",
                "region": [32, 109, 152, 149],
                "status": "readable",
                "content": "Column: W",
            },
            {
                "id": "element-000003",
                "kind": "annotation text line",
                "region": [63, 131, 124, 144],
                "status": "readable",
                "content": "%= 300/364",
            },
        ],
        "relationships": [relationship],
    }
    projection_path = tmp_path / "projection.json"
    projection_path.write_text(
        json.dumps(projection, indent=2, sort_keys=True) + "\n"
    )
    projection_sha256 = START_INTAKE._digest_bytes(projection_path.read_bytes())
    answers = iter([
        "fresh-questioner",
        "pytest-gap-question",
        "operator_text",
        "element-000001",
        "element-000003",
    ])
    messages: list[str] = []

    result = START_INTAKE.gap_clarification.run_round(
        tmp_path / "round-000001",
        projection_path=projection_path,
        projection_sha256=projection_sha256,
        purpose=REAL_PURPOSE,
        contract=4,
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )

    assert result["schema_version"] == 4
    assert [
        item["id"] for item in result["gaps"][0]["recorded_context"]
    ] == ["element-000002", "element-000003"]
    assert result["questions"][0]["asks"] == (
        "Which recorded element is the intended origin for relationship-000003: "
        "element-000003 (\u201c%= 300/364\u201d) or element-000002 (\u201cColumn: W\u201d)?"
    )
    assert messages == [
        "Invalid answer: gap_candidate_000001: choose one of: "
        "element-000002, element-000003."
    ]
    journal = [
        json.loads(line)
        for line in (
            tmp_path / "round-000001" / "interview.jsonl"
        ).read_text().splitlines()
    ]
    rejected = [
        entry for entry in journal
        if entry["event"] == "answer_recorded" and not entry["accepted"]
    ]
    assert len(rejected) == 1
    assert rejected[0]["raw"] == "element-000001"


@pytest.mark.parametrize("candidate_ids", [[], ["element-000001"]])
def test_relationship_gap_without_a_real_candidate_choice_uses_ordinary_clarification(
    candidate_ids: list[str],
) -> None:
    projection = {
        "elements": [{
            "id": "element-000001",
            "kind": "annotation callout",
            "status": "readable",
            "content": "Only containing element",
        }],
        "relationships": [{
            "id": "relationship-000001",
            "kind": "visible relationship",
            "from_id": "element-000001",
            "to_id": None,
            "status": "gap",
            "description": "",
            "gap_reason": "No distinct readable endpoint was recorded.",
            "binding_issue": {
                "participant": "target",
                "matching_element_ids": candidate_ids,
                "point": [10, 10],
                "reason": "recorded_element_not_readable",
            },
        }],
    }

    gaps = START_INTAKE.gap_clarification.select_gaps(
        projection, "a" * 64,
    )

    assert len(gaps) == 1
    assert gaps[0]["id"] == "relationship-000001"
    assert [item["id"] for item in gaps[0]["recorded_context"]] == [
        "element-000001"
    ]
    assert START_INTAKE.gap_clarification._candidate_question_context(
        gaps[0]
    ) is None


def test_all_known_gaps_become_one_operator_question_round_without_overwriting(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, project_source=True)
    producer_answers = iter([
        "test-model", "pytest",
        "yes", "visible-text", "owned_by_active_core",
        "10", "20", "100", "120", "readable",
        "A readable description", "yes",
        "yes", "visible-target", "owned_by_active_core",
        "120", "20", "220", "120", "readable",
        "A readable target", "no",
        "yes", "first-obscured-target", "owned_by_active_core",
        "10", "130", "100", "220", "gap",
        "The first target is obscured.", "no",
        "yes", "second-obscured-target", "owned_by_active_core",
        "120", "130", "220", "220", "gap",
        "The second target is obscured.", "no",
        "no", *(["no"] * 15),
        "contains_claimed_content",
        "use_recorded_endpoint", "visually-connected-to", "origin",
        "10", "20", "120", "20",
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
    assert waiting["question"]["answers_gap"]["id"] == "element-000003"
    assert "questions" not in waiting
    ledger_before_operator_boundary = (work / "ledger.jsonl").read_bytes()
    operator_boundary = START_INTAKE.run_clarification_boundary(work)
    assert operator_boundary["boundary"] == "needs_operator_answer"
    assert operator_boundary["question"] == waiting["question"]
    assert (work / "ledger.jsonl").read_bytes() == ledger_before_operator_boundary
    state = json.loads((work / "intake-state.json").read_text())
    assert [item["answers_gap"]["id"] for item in state["questions"]] == [
        "element-000003", "element-000004",
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
    assert second_question["question"]["answers_gap"]["id"] == "element-000004"
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
    assert ledger[-4]["source"]["answers_gap"]["id"] == "element-000003"
    assert ledger[-2]["source"]["answers_question"] == "gap-clarification-answer-000002"
    assert ledger[-2]["source"]["answers_gap"]["id"] == "element-000004"

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
        "element-000003", "element-000004",
    ]
    assert (work / "ledger.jsonl").read_bytes() == ledger_after_assessment
    assert (work / "intake-state.json").read_bytes() == state_after_assessment
    assert [item["verdict"] for item in assessed["assessments"]] == [
        "does_not_resolve_gap", "does_not_resolve_gap",
    ]
    assert [item["gap"]["id"] for item in assessed["assessments"]] == [
        "element-000003", "element-000004",
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
    projection_answers = iter(
        _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
    )
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
    Image.new("RGB", (40, 40), "white").save(additional, format="PNG")
    additional_bytes = additional.read_bytes()
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
    assert Path(boundary["work"][0]["attachments"][0]) == (
        work
        / "additional-source-projections"
        / "source-000004"
        / "projection-interview"
        / "region-evidence"
        / "region-r01-c01.png"
    )
    assert boundary["work"][0]["command"][-1] == "--run-projection-interview"
    attachment, command = CODEX_RUNNER.load_request(work)
    assert isinstance(attachment, tuple)
    assert attachment == tuple(
        Path(path) for path in boundary["work"][0]["attachments"]
    )
    assert command == boundary["work"][0]["command"]

    additional_projection_answers = iter(
        _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
    )
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
    assert completed_boundary["boundary"] == "needs_model_interview"
    assert completed_boundary["stopped"] == "assessing_additional_source_gap"
    assert completed_boundary["evidence"][0]["projection_id"] == (
        projected["projection"]["id"]
    )
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


def test_projected_additional_image_is_assessed_against_its_exact_original_gap(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "annotated.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    first_answers = iter(
        _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
    )
    START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(first_answers),
        output_fn=lambda _message: None,
    )
    first_verification = iter(_verification_answers(1))
    first_projected = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(first_verification),
        output_fn=lambda _message: None,
    )
    original_projection_path = work / first_projected["projection"]["path"]
    original_projection_before = original_projection_path.read_bytes()

    question_boundary = START_INTAKE.run_clarification_boundary(work)
    assert question_boundary["boundary"] == "needs_model_interview"
    original_gap = json.loads(
        (work / "intake-state.json").read_text()
    )["gap_question_round"]["gaps"][0]
    question_answers = iter([
        "fresh-questioner",
        "pytest-gap-question",
        "local_file",
        "Which additional source shows the exact obscured value?",
    ])
    START_INTAKE.run_gap_clarification(
        work,
        input_fn=lambda _prompt: next(question_answers),
        output_fn=lambda _message: None,
    )
    clean_image = tmp_path / "clean.png"
    Image.new("RGB", (40, 40), "white").save(clean_image, format="PNG")
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_file=clean_image,
    )
    START_INTAKE.run_clarification_boundary(work)
    additional_answers = _projection_answers(
        contract=PROJECTION_INTERVIEW.CONTRACT
    )
    additional_answers[additional_answers.index("A readable description")] = "$48,000"
    additional_iterator = iter(additional_answers)
    START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(additional_iterator),
        output_fn=lambda _message: None,
    )
    additional_verification = iter(_verification_answers(1))
    additional_projected = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(additional_verification),
        output_fn=lambda _message: None,
    )
    additional_projection_path = work / additional_projected["projection"]["path"]
    additional_projection_before = additional_projection_path.read_bytes()

    assessment_boundary = START_INTAKE.run_clarification_boundary(work)
    assert assessment_boundary["boundary"] == "needs_model_interview"
    assert assessment_boundary["stopped"] == "assessing_additional_source_gap"
    assert assessment_boundary["gap"] == original_gap
    assert assessment_boundary["evidence"][0]["item"]["content"] == "$48,000"
    attachments, command = CODEX_RUNNER.load_request(work)
    assert isinstance(attachments, tuple)
    assert [path.name for path in attachments] == ["source-000003", "source-000004"]
    assert command[-1] == "--run-additional-source-gap-assessment"
    runner_boundary = CODEX_RUNNER.run_clarification_boundary(work)
    assert runner_boundary == assessment_boundary
    assert CODEX_RUNNER.next_model_request(work, runner_boundary) == (
        attachments,
        command,
    )
    state_path = work / "intake-state.json"
    state_before_attachment_tamper = state_path.read_bytes()
    duplicate_attachment = work / "sources" / "equal-byte-duplicate"
    duplicate_attachment.write_bytes(clean_image.read_bytes())
    changed_state = json.loads(state_before_attachment_tamper)
    changed_state["additional_source_gap_assessment"]["attachments"][1] = str(
        duplicate_attachment.resolve()
    )
    state_path.write_text(json.dumps(changed_state, indent=2, sort_keys=True) + "\n")
    with pytest.raises(
        CODEX_RUNNER.LaunchError,
        match="attachment identity changed",
    ):
        CODEX_RUNNER.load_request(work)
    state_path.write_bytes(state_before_attachment_tamper)
    duplicate_attachment.unlink()

    messages: list[str] = []
    assessment_answers = iter([
        "fresh-additional-source-assessor",
        "pytest-additional-source-assessment",
        "resolves_gap",
        "invented-evidence",
        "evidence-000001",
        "no_more_evidence",
        "The selected element gives the exact value hidden in the original source.",
    ])
    assessed = START_INTAKE.run_additional_source_gap_assessment(
        work,
        input_fn=lambda _prompt: next(assessment_answers),
        output_fn=messages.append,
    )
    assert assessed["stopped"] == "additional_source_gap_assessment_recorded"
    assert assessed["assessment"]["verdict"] == "resolves_gap"
    assert [item["evidence_id"] for item in assessed["assessment"]["evidence"]] == [
        "evidence-000001"
    ]
    assert assessed["assessment"]["gap"] == assessment_boundary["gap"]
    assert assessed["assessment"]["original_projection"]["sha256"] == (
        assessment_boundary["gap"]["projection_sha256"]
    )
    assert assessed["assessment"]["current_projection"]["sha256"] == (
        first_projected["projection"]["sha256"]
    )
    assert assessed["assessment"]["additional_projection"]["sha256"] == (
        additional_projected["projection"]["sha256"]
    )
    assert assessed["assessment"]["evidence"][0]["collection"] == "elements"
    assert assessed["assessment"]["evidence"][0]["item_id"] == "element-000001"
    assert messages == [
            "Invalid answer: evidence_selection_000001: got 'invented-evidence'; choose one of ['evidence-000001', 'evidence-000002', 'evidence-000003']."
    ]
    assert original_projection_path.read_bytes() == original_projection_before
    assert additional_projection_path.read_bytes() == additional_projection_before
    completed = START_INTAKE.run_clarification_boundary(work)
    assert completed["boundary"] == "clarification_complete"
    assert completed["stopped"] == "clarification_continuation_complete"
    assert completed["terminal_disposition"]["disposition"] == "first_layer_complete"
    assert completed["projection_qualification"]["coverage"][
        "remaining_gap_count"
    ] == 0
    assert completed["source_projection_closure"]["verdict"] == "all_projected"
    admission = json.loads((work / "intake-state.json").read_text())[
        "additional_source_element_gap_admission"
    ]
    assert admission["gap"] == original_gap
    assert admission["selected_evidence"] == assessed["assessment"]["evidence"][0]
    assert completed["projection"]["parent_projection_id"] == (
        first_projected["projection"]["id"]
    )
    assert completed["projection"]["version"] == 2
    assert completed["projection"]["gap_count"] == 0
    assert original_projection_path.read_bytes() == original_projection_before
    assert additional_projection_path.read_bytes() == additional_projection_before

    parent_projection = json.loads(original_projection_before)
    admitted_projection_path = work / completed["projection"]["path"]
    admitted_projection_before = admitted_projection_path.read_bytes()
    admitted_projection = json.loads(admitted_projection_before)
    target = next(
        item
        for item in admitted_projection["elements"]
        if item["id"] == original_gap["id"]
    )
    assert target["status"] == "readable"
    assert target["content"] == "$48,000"
    assert target["gap_reason"] == ""
    assert target["region"] == original_gap["record"]["region"]
    assert [
        item
        for item in admitted_projection["elements"]
        if item["id"] != original_gap["id"]
    ] == [
        item
        for item in parent_projection["elements"]
        if item["id"] != original_gap["id"]
    ]
    assert admitted_projection["relationships"] == parent_projection["relationships"]
    assert admitted_projection["scan_regions"] == parent_projection["scan_regions"]
    assert START_INTAKE.run_clarification_boundary(work) == completed
    assert CODEX_RUNNER.run_clarification_boundary(work) == completed
    closure = START_INTAKE.run_source_projection_closure(work)
    original_source_outcome = next(
        item for item in closure["outcomes"] if item["source_id"] == "source-000003"
    )
    assert closure["verdict"] == "all_projected"
    assert original_source_outcome["projection_version_count"] == 2
    assert original_source_outcome["projection"]["id"] == completed["projection"]["id"]

    ledger = [
        json.loads(line)
        for line in (work / "ledger.jsonl").read_text().splitlines()
    ]
    assert [entry["event"] for entry in ledger[-4:]] == [
        "model_additional_source_gap_assessment_requested",
        "model_additional_source_gap_assessment_completed",
        "projection_version_created",
        "clarification_continuation_completed",
    ]
    assert ledger[-3]["rejected_answer_count"] == 1
    assert ledger[-2]["role"] == "additional_source_element_gap_admission"
    assert ledger[-2]["resolved_gap"] == original_gap
    assert ledger[-2]["selected_evidence"] == assessed["assessment"]["evidence"][0]
    assert ledger[-1]["basis"] == "additional_source_element_gap_admission"
    assessment_path = work / assessed["assessment_path"]
    assessment_before = assessment_path.read_bytes()
    changed = json.loads(assessment_path.read_text())
    changed["assessment"]["evidence"][0]["item"]["content"] = "$47,999"
    assessment_path.write_text(json.dumps(changed, indent=2, sort_keys=True) + "\n")
    tampered = START_INTAKE.run_clarification_boundary(work)
    assert tampered["status"] == "blocked"
    assert tampered["stopped"] == "invalid additional source gap assessment"
    assessment_path.write_bytes(assessment_before)

    admitted_projection_path.write_bytes(b"changed child projection")
    changed_projection = START_INTAKE.run_clarification_boundary(work)
    assert changed_projection["status"] == "blocked"
    assert changed_projection["stopped"] == "immutable projection changed"
    admitted_projection_path.write_bytes(admitted_projection_before)
    assert START_INTAKE.run_clarification_boundary(work) == completed


def test_utf8_additional_source_fills_its_reserved_projection_verbatim(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    projection_answers = iter(
        _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
    )
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

    boundary = START_INTAKE.run_clarification_boundary(work)
    projected_state = json.loads((work / "intake-state.json").read_text())
    projection = projected_state["additional_source_projection"]
    assert boundary["boundary"] == "needs_model_interview"
    assert boundary["stopped"] == "assessing_additional_source_gap"
    assert boundary["evidence"][0]["item"] == {
        "text": "plain text reference\n"
    }
    assessment_answers = iter([
        "fresh-text-assessor",
        "pytest-text-assessment",
        "does_not_resolve_gap",
        "The supplied text does not identify the exact obscured value.",
    ])
    result = START_INTAKE.run_additional_source_gap_assessment(
        work,
        input_fn=lambda _prompt: next(assessment_answers),
        output_fn=lambda _message: None,
    )
    ledger_after = (work / "ledger.jsonl").read_bytes()

    assert result["status"] == "ready_for_projection_assessment"
    assert result["stopped"] == "additional_source_gap_assessment_recorded"
    assert result["assessment"]["verdict"] == "does_not_resolve_gap"
    assert result["assessment"]["evidence"] == []
    assert frozen["projection"]["status"] == "pending"
    assert result["reserved_projection"] == frozen["projection"]
    assert projection["id"] == frozen["projection"]["id"]
    assert projection["method"] == "verbatim_utf8"
    assert projection["coverage"]["status"] == "complete"
    assert (work / projection["path"]).read_bytes() == supplied.read_bytes()
    assert len(ledger_after.decode("utf-8").splitlines()) == len(
        ledger_before.decode("utf-8").splitlines()
    ) + 3
    assert START_INTAKE.run_clarification_boundary(work) == {
        **result,
        "boundary": "additional_source_gap_assessment_complete",
    }
    assert "additional_source_element_gap_admission" not in json.loads(
        (work / "intake-state.json").read_text()
    )
    assert (work / "ledger.jsonl").read_bytes() == ledger_after

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


def test_element_admission_with_another_gap_cannot_finish_the_first_layer(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "annotated.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    first_answers = iter(_projection_answers_with_two_element_gaps())
    START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(first_answers),
        output_fn=lambda _message: None,
    )
    verification = iter(_verification_answers(1))
    first_projected = START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(verification),
        output_fn=lambda _message: None,
    )
    assert first_projected["projection"]["gap_count"] == 2

    START_INTAKE.run_clarification_boundary(work)
    question_answers = iter([
        "fresh-questioner",
        "pytest-gap-question",
        "local_file",
        "Which source shows the first obscured value?",
        "operator_text",
        "What is the second obscured value?",
    ])
    START_INTAKE.run_gap_clarification(
        work,
        input_fn=lambda _prompt: next(question_answers),
        output_fn=lambda _message: None,
    )
    clean_image = tmp_path / "clean.png"
    Image.new("RGB", (40, 40), "white").save(clean_image, format="PNG")
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_file=clean_image,
    )
    START_INTAKE.run_clarification_boundary(work)
    additional_answers = _projection_answers(
        contract=PROJECTION_INTERVIEW.CONTRACT
    )
    additional_answers[additional_answers.index("A readable description")] = "$48,000"
    additional_iterator = iter(additional_answers)
    START_INTAKE.run_first_projection_interview(
        work,
        input_fn=lambda _prompt: next(additional_iterator),
        output_fn=lambda _message: None,
    )
    additional_verification = iter(_verification_answers(1))
    START_INTAKE.run_first_projection_verification(
        work,
        input_fn=lambda _prompt: next(additional_verification),
        output_fn=lambda _message: None,
    )
    START_INTAKE.run_clarification_boundary(work)
    assessment_answers = iter([
        "fresh-additional-source-assessor",
        "pytest-additional-source-assessment",
        "resolves_gap",
        "evidence-000001",
        "no_more_evidence",
        "The selected element gives the exact first hidden value.",
    ])
    START_INTAKE.run_additional_source_gap_assessment(
        work,
        input_fn=lambda _prompt: next(assessment_answers),
        output_fn=lambda _message: None,
    )

    state, entries, load_error = START_INTAKE._load_bound(
        work, b"There is a new intake"
    )
    assert load_error is None and state is not None
    admitted = START_INTAKE._consume_additional_source_element_gap_admission(
        work, state, entries, REAL_PURPOSE
    )
    assert admitted["stopped"] == "additional_source_element_gap_admitted"
    state, entries, load_error = START_INTAKE._load_bound(
        work, b"There is a new intake"
    )
    assert load_error is None and state is not None
    qualification, qualification_error = (
        START_INTAKE._terminal_projection_qualification(work, state)
    )
    assert qualification_error is None and qualification is not None
    changed_qualification = json.loads(json.dumps(qualification))
    changed_qualification["remaining_gaps"][0]["id"] = "element-invented"
    state_before_mismatch = (work / "intake-state.json").read_bytes()
    ledger_before_mismatch = (work / "ledger.jsonl").read_bytes()
    mismatch = START_INTAKE._resume_question_round_after_additional_source_admission(
        work, state, entries, changed_qualification
    )
    assert mismatch["status"] == "blocked"
    assert mismatch["stopped"] == "question round resumption unavailable"
    assert "remaining gaps" in mismatch["why"]
    assert (work / "intake-state.json").read_bytes() == state_before_mismatch
    assert (work / "ledger.jsonl").read_bytes() == ledger_before_mismatch

    resumed = START_INTAKE.run_clarification_boundary(work)

    assert resumed["boundary"] == "needs_operator_answer"
    assert resumed["stopped"] == "awaiting_gap_answers"
    assert resumed["answered_question_count"] == 1
    assert resumed["question_count"] == 2
    assert resumed["question"]["asks"] == "What is the second obscured value?"
    assert resumed["question"]["answers_gap"]["id"] == "element-000004"
    assert CODEX_RUNNER.run_clarification_boundary(work) == resumed
    ledger_events = [
        json.loads(line)["event"]
        for line in (work / "ledger.jsonl").read_text().splitlines()
    ]
    assert ledger_events[-2:] == [
        "operator_question_fulfilled_by_additional_source",
        "operator_question_asked",
    ]
    assert "clarification_continuation_completed" not in ledger_events

    answered = START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda _prompt: "The second value is 29.0%.",
        output_fn=lambda _message: None,
    )
    assert answered["stopped"] == "gap_question_round_answered"
    assert answered["answered_question_count"] == 2

    assessment_requested = START_INTAKE.run_clarification_boundary(work)
    assert assessment_requested["boundary"] == "needs_model_interview"
    assert assessment_requested["stopped"] == "assessing_gap_answers"
    assessment_state = json.loads((work / "intake-state.json").read_text())
    request = assessment_state["gap_answer_assessment"]
    assert request["assessment_count"] == 2
    assert request["model_assessment_count"] == 1
    assert [item["mode"] for item in request["assessment_plan"]] == [
        "admitted_source",
        "model",
    ]
    assert [item["round_position"] for item in request["assessment_plan"]] == [
        1,
        2,
    ]
    assert [item["position"] for item in request["bindings"]] == [1]

    plan_tamper = tmp_path / "mixed-assessment-plan-tamper"
    shutil.copytree(work, plan_tamper)
    tampered_state_path = plan_tamper / "intake-state.json"
    tampered_state = json.loads(tampered_state_path.read_text())
    tampered_state["gap_answer_assessment"]["assessment_plan"].reverse()
    tampered_state_path.write_text(
        json.dumps(tampered_state, indent=2, sort_keys=True) + "\n"
    )
    tampered_ledger = (plan_tamper / "ledger.jsonl").read_bytes()
    tampered = START_INTAKE.run_gap_answer_assessment(plan_tamper)
    assert tampered["status"] == "blocked"
    assert tampered["stopped"] == "invalid ledger"
    assert "request changed" in tampered["why"]
    assert (plan_tamper / "ledger.jsonl").read_bytes() == tampered_ledger

    resolving_element = tmp_path / "resolving-operator-text-element"
    shutil.copytree(work, resolving_element)
    resolving_answers = iter([
        "fresh-resolving-element-assessor",
        "pytest-resolving-element-assessment",
        "resolves_gap",
        "The operator supplied the exact value for this element.",
    ])
    resolving_assessed = START_INTAKE.run_gap_answer_assessment(
        resolving_element,
        input_fn=lambda _prompt: next(resolving_answers),
        output_fn=lambda _message: None,
    )
    assert resolving_assessed["stopped"] == "gap_answer_assessment_recorded"
    assert resolving_assessed["continuation"]["decision"] == (
        "apply_resolving_answer"
    )
    parent_record = json.loads(
        (resolving_element / "intake-state.json").read_text()
    )["current_projection"]
    parent_bytes = (resolving_element / parent_record["path"]).read_bytes()

    changed_answer = tmp_path / "resolving-element-answer-tamper"
    shutil.copytree(resolving_element, changed_answer)
    changed_answer_state = json.loads(
        (changed_answer / "intake-state.json").read_text()
    )
    changed_answer_projection = changed_answer_state["gap_question_answers"][1][
        "projection"
    ]
    (changed_answer / changed_answer_projection["path"]).write_text("changed")
    changed_answer_ledger = (changed_answer / "ledger.jsonl").read_bytes()
    rejected_admission = START_INTAKE.run_clarification_boundary(changed_answer)
    assert rejected_admission["status"] == "blocked"
    assert "answer source, projection, or question changed" in rejected_admission[
        "why"
    ]
    assert (changed_answer / "ledger.jsonl").read_bytes() == changed_answer_ledger

    resolved = CODEX_RUNNER.run_clarification_boundary(resolving_element)
    assert resolved["boundary"] == "clarification_complete"
    assert resolved["terminal_disposition"]["disposition"] == (
        "first_layer_complete"
    )
    resolved_state = json.loads(
        (resolving_element / "intake-state.json").read_text()
    )
    admissions = resolved_state["operator_text_element_gap_admissions"]
    assert len(admissions) == 1
    admission = admissions[0]
    assert admission["assessment_round"] == 1
    assert admission["assessment_position"] == 2
    assert admission["answer_source"]["sha256"] == (
        admission["answer_projection"]["sha256"]
    )
    assert admission["answer_text"] == "The second value is 29.0%."
    assert (resolving_element / parent_record["path"]).read_bytes() == parent_bytes
    child_path = resolving_element / admission["projection"]["path"]
    child = json.loads(child_path.read_text())
    resolved_elements = [
        item for item in child["elements"] if item["id"] == "element-000004"
    ]
    assert len(resolved_elements) == 1
    assert resolved_elements[0]["status"] == "readable"
    assert resolved_elements[0]["content"] == "The second value is 29.0%."
    assert resolved_elements[0]["resolution_audit"]["assessment_round"] == 1
    assert resolved_elements[0]["resolution_audit"]["assessment_position"] == 2
    projection_events = [
        json.loads(line)
        for line in (resolving_element / "ledger.jsonl").read_text().splitlines()
        if json.loads(line)["event"] == "projection_version_created"
        and json.loads(line).get("role") == "operator_text_element_gap_admission"
    ]
    assert len(projection_events) == 1
    assert projection_events[0]["admission_input_sha256"] == admission[
        "input_sha256"
    ]
    for name in ("missing", "duplicated"):
        history_tamper = tmp_path / f"operator-text-admission-{name}"
        shutil.copytree(resolving_element, history_tamper)
        history_state_path = history_tamper / "intake-state.json"
        history_state = json.loads(history_state_path.read_text())
        if name == "missing":
            history_state.pop("operator_text_element_gap_admissions")
        else:
            history_state["operator_text_element_gap_admissions"].append(
                json.loads(json.dumps(
                    history_state["operator_text_element_gap_admissions"][0]
                ))
            )
        history_state_path.write_text(
            json.dumps(history_state, indent=2, sort_keys=True) + "\n"
        )
        history_ledger = (history_tamper / "ledger.jsonl").read_bytes()
        rejected_history = START_INTAKE.run_clarification_boundary(history_tamper)
        assert rejected_history["status"] == "blocked"
        assert rejected_history["stopped"] in {
            "invalid operator-text element admission",
            "immutable projection changed",
        }
        assert (history_tamper / "ledger.jsonl").read_bytes() == history_ledger

    mixed_assessment_answers = iter([
        "fresh-mixed-assessor",
        "pytest-mixed-assessment",
        "does_not_resolve_gap",
        "The text supplies a value but does not identify the exact visible element.",
    ])
    assessed = START_INTAKE.run_gap_answer_assessment(
        work,
        input_fn=lambda _prompt: next(mixed_assessment_answers),
        output_fn=lambda _message: None,
    )
    assert assessed["stopped"] == "gap_answer_assessment_recorded"
    assert assessed["continuation"]["decision"] == "prepare_next_round"
    assert [item["position"] for item in assessed["assessments"]] == [1, 2]
    assert [item["verdict"] for item in assessed["assessments"]] == [
        "resolves_gap",
        "does_not_resolve_gap",
    ]
    assert assessed["assessments"][0]["basis"]["kind"] == "admitted_source"
    assert assessed["assessments"][0]["basis"][
        "accepted_assessment_result_sha256"
    ] == assessment_state["gap_question_answers"][0]["fulfillment"][
        "assessment_result_sha256"
    ]
    assert "basis" not in assessed["assessments"][1]
    model_result = json.loads((
        work / "gap-answer-assessments" / "round-000001" / "assessment.json"
    ).read_text())
    assert model_result["assessment_count"] == 1
    assert model_result["assessments"][0]["gap"]["id"] == "element-000004"
    completion = json.loads((work / "ledger.jsonl").read_text().splitlines()[-1])
    assert completion["event"] == "model_gap_answer_assessment_completed"
    assert completion["assessment_count"] == 2
    assert completion["model_assessment_count"] == 1
    next_round = START_INTAKE.run_clarification_boundary(work)
    assert next_round.get("boundary") == "needs_model_interview", next_round
    assert next_round["stopped"] == "formulating_follow_up_gap_question_round"
    assert next_round["round"] == 2

def test_url_typed_question_freezes_and_projects_one_additional_public_url(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    projection_answers = iter(
        _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
    )
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
    projected_state = json.loads((work / "intake-state.json").read_text())
    projection = projected_state["additional_source_projection"]

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
    assert completed["boundary"] == "needs_model_interview"
    assert completed["stopped"] == "assessing_additional_source_gap"
    assert completed["evidence"][0]["item"] == {
        "text": content.decode("utf-8")
    }
    assert projection["id"] == frozen["projection"]["id"]
    assert projection["method"] == "verbatim_utf8"
    assert (work / projection["path"]).read_bytes() == content
    closure = START_INTAKE.run_source_projection_closure(work)
    assert closure["verdict"] == "all_projected"
    assert closure["outcome_counts"] == {
        "projected": 4,
        "pending": 0,
        "failed": 0,
    }
    assert len((work / "ledger.jsonl").read_bytes().splitlines()) == (
        len(ledger_after_freeze.splitlines()) + 2
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
    clarification["gap"] = next(
        gap
        for gap in START_INTAKE.gap_clarification.select_gaps(
            projection, inputs["projection_sha256"]
        )
        if gap["collection"] == "relationships"
    )
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


def test_missing_participant_contract_preserves_a_locked_unreadable_endpoint() -> None:
    """Captured source-000003-v3 shape: relationship knowledge can outgrow text legibility."""
    projection = {
        "elements": [{
            "capture_scope": "region-r04-c02",
            "content": "",
            "gap_reason": (
                "The text is clipped by the source at the left, right, and bottom "
                "edges, so the full sentence is not visible."
            ),
            "id": "element-000020",
            "kind": "explanatory text",
            "region": [0, 974, 1000, 1000],
            "scan_region_id": "region-r04-c02",
            "status": "gap",
        }],
    }
    relationship = {
        "description": "",
        "from_id": "element-000020",
        "gap_reason": (
            "The explanatory sentence is clipped by the source at the left, right, "
            "and bottom edges, so its full text and the endpoint or relationship it "
            "identifies are not visible."
        ),
        "id": "relationship-000015",
        "kind": "explanatory footer text",
        "participant_id": "element-000020",
        "status": "gap",
        "to_id": None,
    }

    contract = START_INTAKE.gap_resolution._participant_contract(
        projection, relationship
    )

    assert contract == {
        "mode": "missing_participant",
        "unresolved_role": "target",
        "known_role": "origin",
        "known_id": "element-000020",
        "known_point": None,
        "known_status": "gap",
    }
    assert projection["elements"][0]["status"] == "gap"
    assert projection["elements"][0]["content"] == ""


def test_operator_answer_resolves_relationship_without_rewriting_unreadable_endpoint(
    tmp_path: Path,
) -> None:
    inputs = _missing_endpoint_resolution_fixture(tmp_path)
    projection = json.loads(inputs["projection_path"].read_text())
    projection["elements"][0] = {
        "capture_scope": "region-r04-c02",
        "content": "",
        "gap_reason": (
            "The text is clipped by the source at the left, right, and bottom "
            "edges, so the full sentence is not visible."
        ),
        "id": "element-000001",
        "kind": "explanatory text",
        "region": [0, 974, 1000, 1000],
        "scan_region_id": "region-r04-c02",
        "status": "gap",
    }
    relationship = projection["relationships"][0]
    relationship.update({
        "from_id": "element-000001",
        "to_id": None,
        "participant_id": "element-000001",
        "kind": "explanatory footer text",
        "gap_reason": (
            "The explanatory sentence is clipped, so the endpoint or relationship "
            "it identifies is not visible."
        ),
    })
    inputs["projection_path"].write_text(
        json.dumps(projection, indent=2, sort_keys=True) + "\n"
    )
    inputs["projection_sha256"] = START_INTAKE._digest_bytes(
        inputs["projection_path"].read_bytes()
    )
    clarification = json.loads(inputs["clarification_path"].read_text())
    clarification["gap"] = next(
        gap
        for gap in START_INTAKE.gap_clarification.select_gaps(
            projection, inputs["projection_sha256"]
        )
        if gap["collection"] == "relationships"
    )
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
        "reason": "The answer identifies the history list and its search behavior.",
    }
    clarification["prior_rejection"] = {
        "attempt": 3,
        "candidate_sha256": "a" * 64,
        "verification_result_sha256": "b" * 64,
        "verification_verdict": "not_supported",
        "verification_reason": "The proposed target was the rejected heading.",
        "rejected_relationship": {
            "resolution_of": relationship["id"],
        },
    }
    inputs["clarification_path"].write_text(
        json.dumps(clarification, indent=2, sort_keys=True) + "\n"
    )
    inputs["clarification_sha256"] = START_INTAKE._digest_bytes(
        inputs["clarification_path"].read_bytes()
    )
    answers = iter([
        "fresh-resolver",
        "captured-gap-endpoint",
        "use_recorded_element",
        "element-000003",
        "700",
        "100",
        "500",
        "990",
        "The clipped footer describes the payout history list and search behavior.",
    ])

    result = START_INTAKE.gap_resolution.run(
        tmp_path / "preserved-gap-endpoint-resolution",
        **inputs,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    candidate = json.loads(
        (
            tmp_path
            / "preserved-gap-endpoint-resolution"
            / "verification-candidate.json"
        ).read_text()
    )

    assert result["verdict"] == "resolves_gap"
    locked = next(
        item for item in candidate["elements"] if item["id"] == "element-000001"
    )
    assert locked == projection["elements"][0]
    resolved = candidate["relationships"][0]
    assert resolved["status"] == "readable"
    assert resolved["from_id"] == "element-000001"
    assert resolved["to_id"] == "element-000003"
    assert resolved["binding_method"] == (
        "verifier_rejection_corrected_missing_participant_with_locked_endpoint"
    )
    assert resolved["resolution_evidence"]["locked_known_element_status"] == "gap"
    assert resolved["resolution_evidence"]["rejected_candidate_sha256"] == "a" * 64


def _terminal_projection_fixture(
    tmp_path: Path, *, incomplete: bool = False
) -> tuple[dict[str, object], dict[str, object]]:
    regions = START_INTAKE.projection_interview._scan_regions()
    for region in regions:
        region["status"] = "scanned"
        region["deferred_context_candidates"] = []
        region["context_candidate_obligations"] = []
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


def _terminal_context_deferral_fixture(
    tmp_path: Path, *, pending: bool = False, gap: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
    projection, state = _terminal_projection_fixture(tmp_path)
    regions = projection["scan_regions"]
    for region in regions:
        region["deferred_context_candidates"] = []
        region["context_candidate_obligations"] = []
    element = projection["elements"][1]
    regions[0]["element_ids"].remove(element["id"])
    regions[1]["element_ids"].append(element["id"])
    element.update({
        "region": [260, 10, 350, 100],
        "capture_scope": regions[1]["id"],
        "scan_region_id": regions[1]["id"],
        "status": "gap" if gap else "readable",
        "content": "" if gap else "$8,100",
        "gap_reason": "deferred field is unreadable" if gap else "",
    })
    regions[0]["deferred_context_candidates"].append({
        "obligation_id": "context-obligation-000001",
        "owner_region_id": regions[1]["id"],
        "anchor": [280, 20],
        "candidate_kind": "field",
        "reason": "context_only",
        "crop_sha256": "b" * 64,
        "guide_sha256": "c" * 64,
    })
    regions[0]["evidence"] = {
        "crop_sha256": "b" * 64,
        "guide_sha256": "c" * 64,
    }
    regions[1]["context_candidate_obligations"].append({
        "id": "context-obligation-000001",
        "source_region_id": regions[0]["id"],
        "candidate_kind": "field",
        "anchor": [280, 20],
        "status": "pending" if pending else "resolved",
        "resolution": None if pending else "gap" if gap else "element",
        "element_id": None if pending else element["id"],
        "gap_reason": "" if pending or not gap else "deferred field is unreadable",
    })
    projection_path = tmp_path / state["current_projection"]["path"]
    projection_path.write_text(
        json.dumps(projection, indent=2, sort_keys=True) + "\n"
    )
    record = state["current_projection"]
    record["sha256"] = START_INTAKE._digest_bytes(projection_path.read_bytes())
    record["gap_count"] = sum(
        item["status"] == "gap"
        for collection in (
            projection["scan_regions"],
            projection["elements"],
            projection["relationships"],
        )
        for item in collection
    )
    return projection, state


def test_terminal_rejects_pending_context_candidate_obligation(
    tmp_path: Path,
) -> None:
    _, state = _terminal_context_deferral_fixture(tmp_path, pending=True)

    qualification, error = START_INTAKE._terminal_projection_qualification(
        tmp_path, state,
    )

    assert qualification is None
    assert error["status"] == "blocked"
    assert error["stopped"] == "terminal_invalid"
    assert "context obligation context-obligation-000001 is not resolved" in error[
        "why"
    ]


def test_verified_gap_projection_can_reopen_independent_source_collection(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    source = tmp_path / "source.xlsx"
    source.write_bytes(_representative_workbook_bytes())
    opening = "There is a new intake"
    purpose = REAL_PURPOSE
    _advance_to_first_source(work)
    START_INTAKE.drive(work, opening, purpose, source)
    projected = START_INTAKE.drive(
        work, opening, purpose, project_source=True
    )
    assert projected["stopped"] == "first_spreadsheet_projection_recorded"
    state = json.loads((work / "intake-state.json").read_text())
    state.update({
        "status": "ready_for_projection_assessment",
        "phase": "gap_resolution_applied",
        "waiting_for": None,
        "question": None,
    })
    (work / "intake-state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n"
    )

    result = START_INTAKE.drive(
        work,
        opening,
        purpose,
        begin_source_collection=True,
    )

    assert result["status"] == "needs_operator"
    assert result["stopped"] == "awaiting_source_collection_decision"
    assert result["question"]["allowed_values"] == [
        "add_source",
        "finish_sources",
    ]


def test_terminal_context_deferral_chain_qualifies_complete_and_gap_outcomes(
    tmp_path: Path,
) -> None:
    complete_work = tmp_path / "complete"
    complete_work.mkdir()
    _, complete_state = _terminal_context_deferral_fixture(complete_work)
    complete, complete_error = START_INTAKE._terminal_projection_qualification(
        complete_work, complete_state,
    )

    assert complete_error is None
    assert complete["qualification"] == "readable_projection_complete"
    assert complete["coverage"]["context_candidate_obligation_count"] == 1
    assert complete["coverage"]["closed_context_candidate_obligation_count"] == 1

    gap_work = tmp_path / "gap"
    gap_work.mkdir()
    _, gap_state = _terminal_context_deferral_fixture(gap_work, gap=True)
    incomplete, incomplete_error = START_INTAKE._terminal_projection_qualification(
        gap_work, gap_state,
    )

    assert incomplete_error is None
    assert incomplete["qualification"] == "readable_projection_incomplete"
    assert [(item["collection"], item["id"]) for item in incomplete["remaining_gaps"]] == [
        ("elements", "element-000002")
    ]


@pytest.mark.parametrize(
    ("case", "why"),
    [
        ("missing", "identities differ"),
        ("duplicated", "is duplicated"),
        ("mismatched", "contradicts its deferral"),
        ("altered", "anchor is not in the source region's context-only area"),
        ("contradictory", "has invalid gap evidence"),
        ("invalid_owner_type", "names an unknown owner region"),
        ("invalid_resolution_type", "has an invalid resolution"),
        ("missing_ledger", "context-deferral ledger is missing"),
        ("evidence_mismatch", "contradicts its source evidence"),
    ],
)
def test_terminal_context_deferral_chain_rejects_rehashed_conflicts(
    tmp_path: Path, case: str, why: str,
) -> None:
    projection, state = _terminal_context_deferral_fixture(tmp_path)
    source = projection["scan_regions"][0]["deferred_context_candidates"]
    owner = projection["scan_regions"][1]["context_candidate_obligations"]
    if case == "missing":
        owner.clear()
    elif case == "duplicated":
        source.append(json.loads(json.dumps(source[0])))
    elif case == "mismatched":
        owner[0]["candidate_kind"] = "different field"
    elif case == "altered":
        source[0]["anchor"] = [700, 700]
    elif case == "contradictory":
        owner[0].update({
            "resolution": "gap",
            "gap_reason": "claimed gap without a gap element",
        })
    elif case == "invalid_owner_type":
        source[0]["owner_region_id"] = []
    elif case == "invalid_resolution_type":
        owner[0]["resolution"] = []
    elif case == "missing_ledger":
        projection["scan_regions"][2].pop("context_candidate_obligations")
    else:
        source[0]["crop_sha256"] = "d" * 64
    projection_path = tmp_path / state["current_projection"]["path"]
    projection_path.write_text(
        json.dumps(projection, indent=2, sort_keys=True) + "\n"
    )
    state["current_projection"]["sha256"] = START_INTAKE._digest_bytes(
        projection_path.read_bytes()
    )

    qualification, error = START_INTAKE._terminal_projection_qualification(
        tmp_path, state,
    )

    assert qualification is None
    assert error["status"] == "blocked"
    assert error["stopped"] == "terminal_invalid"
    assert why in error["why"]


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
        "context_candidate_obligation_count": 0,
        "closed_context_candidate_obligation_count": 0,
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


def test_clarification_boundary_rejects_undeclared_external_work() -> None:
    model = START_INTAKE._clarification_boundary_result(
        {
            "status": "waiting_for_model",
            "stopped": "assessing_intake_purpose",
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


def test_gap_resolution_can_bind_both_missing_participants_from_recorded_elements() -> None:
    projection = {
        "source_sha256": "a" * 64,
        "elements": [
            {
                "id": "element-formula",
                "kind": "formula annotation",
                "region": [10, 10, 30, 30],
                "status": "readable",
                "content": "Sum Column AE across locations",
            },
            {
                "id": "element-metric",
                "kind": "dashboard metric",
                "region": [60, 60, 90, 90],
                "status": "readable",
                "content": "587 transactions today",
            },
        ],
        "relationships": [],
    }
    relationship = {
        "id": "relationship-gap",
        "kind": "required participant relationship",
        "from_id": None,
        "to_id": None,
        "participant_id": "element-rejected",
        "status": "gap",
        "description": "",
        "gap_reason": "The proposed visible unit was a different source unit.",
        "identity_mismatch": {
            "required_claim": "Sum Column AE across locations",
            "proposed_content": "Sum Column AF across locations",
            "verdict": "different_source_unit",
        },
    }

    contract = START_INTAKE.gap_resolution._participant_contract(
        projection, relationship
    )

    assert contract == {"mode": "missing_both_participants"}
    clarification = {
        "question": {"id": "question-1", "asks": "Which relationship is correct?"},
        "gap": {"record_sha256": "b" * 64},
        "accepted_assessment": {"reason": "The answer establishes the relationship."},
    }
    state = {
        "draft": {
            "verdict": "resolves_gap",
            "reason": "The answer establishes the relationship.",
            "missing_origin_element_id": "element-formula",
            "missing_target_element_id": "element-metric",
            "missing_origin_x": 20,
            "missing_origin_y": 20,
            "missing_target_x": 75,
            "missing_target_y": 75,
            "description": "The formula annotation defines the displayed metric.",
        }
    }
    candidate = START_INTAKE.gap_resolution._candidate(
        projection,
        clarification,
        relationship,
        "c" * 64,
        state,
    )
    assert candidate["relationships"][0]["from_id"] == "element-formula"
    assert candidate["relationships"][0]["to_id"] == "element-metric"
    assert candidate["relationships"][0]["binding_method"] == (
        "accepted_assessment_selected_both_recorded_participants"
    )


def test_gap_resolution_reuses_complete_readable_endpoints_from_stale_gap() -> None:
    projection = {
        "source_sha256": "a" * 64,
        "elements": [
            {
                "id": "element-formula",
                "kind": "formula annotation",
                "region": [10, 10, 30, 30],
                "status": "readable",
                "content": "AE YTD divided by guest count YTD",
            },
            {
                "id": "element-metric",
                "kind": "dashboard metric",
                "region": [60, 60, 90, 90],
                "status": "readable",
                "content": "18.2%",
            },
        ],
        "relationships": [],
    }
    relationship = {
        "id": "relationship-gap",
        "kind": "defines calculation for",
        "from_id": "element-formula",
        "to_id": "element-metric",
        "origin_point": [20, 20],
        "target_point": [75, 75],
        "status": "gap",
        "description": "",
        "gap_reason": "The origin was previously unreadable.",
        "binding_issue": {
            "participant": "origin",
            "matching_element_ids": [],
            "reason": "recorded_element_not_readable",
        },
    }

    contract = START_INTAKE.gap_resolution._participant_contract(
        projection, relationship
    )

    assert contract == {
        "mode": "complete_recorded_participants",
        "origin_id": "element-formula",
        "target_id": "element-metric",
        "origin_point": [20, 20],
        "target_point": [75, 75],
    }
    clarification = {
        "question": {"id": "question-1", "asks": "Is this relationship correct?"},
        "gap": {"record_sha256": "b" * 64},
        "accepted_assessment": {"reason": "The answer confirms the relationship."},
    }
    state = {
        "draft": {
            "verdict": "resolves_gap",
            "reason": "The answer confirms the relationship.",
            "description": "The formula annotation defines the displayed metric.",
        }
    }
    candidate = START_INTAKE.gap_resolution._candidate(
        projection,
        clarification,
        relationship,
        "c" * 64,
        state,
    )
    assert candidate["relationships"][0]["from_id"] == "element-formula"
    assert candidate["relationships"][0]["to_id"] == "element-metric"
    assert candidate["relationships"][0]["binding_method"] == (
        "accepted_assessment_reused_complete_recorded_participants"
    )


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


def test_retry_resolution_keeps_locked_endpoint_and_reselects_only_missing_participant(
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
        "verification_reason": "The rejected proposal selected the wrong missing origin.",
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
        "use_recorded_element",
        "element-000001",
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
        "verifier_rejection_corrected_missing_participant_with_locked_endpoint"
    )
    assert questions[2]["choices"] == [
        "use_recorded_element", "record_visible_element"
    ]
    assert questions[3]["choices"] == ["element-000001", "element-000002"]
    assert questions[2]["context"]["prior_rejection"]["verification_reason"] == (
        "The rejected proposal selected the wrong missing origin."
    )
    evidence = candidate["relationships"][0]["resolution_evidence"]
    assert evidence["locked_known_role"] == "target"
    assert evidence["locked_known_element_id"] == "element-000003"
    assert evidence["locked_known_element_status"] == "readable"


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


def test_recovery_invalidated_retry_does_not_double_consume_captured_assessment() -> None:
    rejected = {
        "attempt": 3,
        "mode": "assessed_answer",
        "selected_assessment_round": 1,
        "selected_assessment_position": 4,
        "candidate_sha256": "1a9f5269bcba8ad5ab4bc26808adc941427c0aeb08b80de384f1796e14caef1d",
        "result_sha256": "d86170a643a6b0ca0eb850f4747d4d0927bf97ff15e39e2c72c3f643eb978e1b",
        "verification_result_sha256": "5c82798aa197acd8792c39885b65c2917538163cb4206d653325f0f94198d8fc",
        "verification_verdict": "not_supported",
        "verification_reason": "The proposed target is the rejected heading.",
        "accepted_assessment_sha256": "b1961aa1b8485c318642f55e1c75d154541ca648fd552eff08cd216fd4366c39",
        "operator_answer_source_sha256": "0769e7917a4fc9f98e8ec237ee31e289044c71c86e10835113beaffbb2ff2bb7",
        "operator_answer_projection_sha256": "0769e7917a4fc9f98e8ec237ee31e289044c71c86e10835113beaffbb2ff2bb7",
    }
    invalidated = {
        **rejected,
        "attempt": 4,
        "candidate_sha256": "3e08db9a173cffea33fd3c764093a7242e9d9d675b7c583c29eb83141858dad6",
        "result_sha256": "cbd106741ac1cd6ec45b5043fc215c83d0022d04f58dd66e120bde7da27e9793",
        "verification_result_sha256": "41de56a01810de8cd3d3e07d622bbf381c2e870ce89e71613ad6779f044b8015",
        "verification_verdict": "supported",
        "verification_reason": "The legacy retry was admitted after dropping the locked participant.",
        "retry_of": {
            "attempt": 3,
            "candidate_sha256": rejected["candidate_sha256"],
            "resolution_result_sha256": rejected["result_sha256"],
            "verification_result_sha256": rejected["verification_result_sha256"],
            "verification_verdict": rejected["verification_verdict"],
            "verification_reason": rejected["verification_reason"],
        },
    }
    corrected = {
        **invalidated,
        "attempt": 5,
        "candidate_sha256": "5964cbb1a61ea7ce05452317f87ed94201fff4cce202e88bd7a6a948b1bba533",
        "result_sha256": "14edea2c3f05e426e6c7a12177ee77d7a4a1cd76c2bcfee056c9a9ed4920fb1f",
        "verification_result_sha256": "454bcd350554f6f18418115fd7dfd553e0129b5b25cd8c3154dbed26df55c9b1",
        "verification_reason": "The corrected relationship retains the locked gap participant.",
        "retry_of": invalidated["retry_of"],
    }

    identities, error = START_INTAKE._consumed_assessment_identities(
        [rejected, invalidated, corrected], invalidated_attempts={4}
    )

    assert error is None
    assert identities == {(1, 4)}


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
        "locked_known_element_status": "readable",
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


def test_relationship_endpoint_claim_waits_for_independent_crop_verdict(
    tmp_path: Path,
) -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["endpoint_crop_verification_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "element_content"
    state["current"] = {
        "capture_scope": "relationship_endpoint",
        "return_stage": "relationship_target_x",
        "kind": "dashboard average-revenue-per-transaction metric",
        "left": 363,
        "top": 416,
        "right": 407,
        "bottom": 442,
        "status": "readable",
    }

    PROJECTION_INTERVIEW._advance(
        state,
        "element_content",
        "$22.25 avg / transaction",
        contract=12,
    )

    assert state["stage"] == "element_content_crop_verdict"
    assert state["elements"] == []
    assert state["current"]["content"] == "$22.25 avg / transaction"


def test_failed_endpoint_crop_stays_as_gap_and_reopens_capture(
) -> None:
    verdict = "does_not_contain_claimed_content"
    gap_reason = "The claimed content is not visible inside the claimed source bounds."
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["endpoint_crop_verification_enabled"] = True
    state["contextual_endpoint_verification_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "element_content_crop_verdict"
    state["relationship_draft"] = {"kind": "visible arrow"}
    state["current"] = {
        "capture_scope": "relationship_endpoint",
        "return_stage": "relationship_target_x",
        "kind": "dashboard average-revenue-per-transaction metric",
        "left": 363,
        "top": 416,
        "right": 407,
        "bottom": 442,
        "status": "readable",
        "content": "$22.25 avg / transaction",
    }
    bounds = [363, 416, 407, 442]
    state["current"]["endpoint_crop_evidence"] = {
        "candidate_id": "element-000001",
        "source_sha256": "6" * 64,
        "source_pixel_size": [1653, 1232],
        "normalized_bounds": bounds,
        "pixel_bounds": PROJECTION_INTERVIEW._pixel_bounds(
            bounds, width=1653, height=1232,
        ),
        "crop_path": "endpoint-evidence/element-000001.png",
        "crop_sha256": "7" * 64,
        "claimed_content": "$22.25 avg / transaction",
        "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
    }

    PROJECTION_INTERVIEW._advance(
        state,
        "element_content_crop_verdict",
        verdict,
        contract=12,
    )

    assert state["stage"] == "element_kind"
    assert state["relationship_draft"] == {"kind": "visible arrow"}
    assert state["elements"] == [{
        "id": "element-000001",
        "kind": "dashboard average-revenue-per-transaction metric",
        "region": bounds,
        "status": "gap",
        "content": "",
        "gap_reason": gap_reason,
        "capture_scope": "relationship_endpoint",
        "endpoint_verification": {
            "verdict": verdict,
            "claimed_content": "$22.25 avg / transaction",
            "evidence": state["elements"][0]["endpoint_verification"]["evidence"],
        },
    }]


def test_relationship_endpoint_rejects_a_multi_field_section_before_binding() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["endpoint_crop_verification_enabled"] = True
    state["endpoint_selector_context_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "element_content"
    state["relationship_draft"] = {"kind": "visible arrow"}
    state["current"] = {
        "capture_scope": "relationship_endpoint",
        "return_stage": "relationship_target_x",
        "kind": "dashboard section",
        "left": 172,
        "top": 516,
        "right": 840,
        "bottom": 654,
        "status": "readable",
    }

    PROJECTION_INTERVIEW._advance(
        state,
        "element_content",
        "Period Summary containing earned to date, projected close, next payout, and last period total",
        contract=12,
    )

    assert state["stage"] == "relationship_endpoint_specificity"
    question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    assert question["choices"] == [
        "one_precise_visible_element",
        "multiple_independent_visible_elements",
    ]

    PROJECTION_INTERVIEW._advance(
        state,
        "relationship_endpoint_specificity",
        "multiple_independent_visible_elements",
        contract=12,
    )

    assert state["stage"] == "element_kind"
    assert state["relationship_draft"] == {"kind": "visible arrow"}
    assert state["elements"][0]["region"] == [172, 516, 840, 654]
    assert state["elements"][0]["status"] == "gap"
    assert state["elements"][0]["endpoint_verification"]["verdict"] == (
        "multiple_independent_visible_elements"
    )


def test_relationship_endpoint_uses_precise_selector_with_separate_context() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["endpoint_crop_verification_enabled"] = True
    state["contextual_endpoint_verification_enabled"] = True
    state["endpoint_context_evidence_enabled"] = True
    state["endpoint_selector_context_enabled"] = True
    state["endpoint_identity_context_choice_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "element_content"
    state["relationship_draft"] = {"kind": "visible arrow"}
    state["current"] = {
        "capture_scope": "relationship_endpoint",
        "return_stage": "relationship_target_x",
        "kind": "dashboard value",
        "left": 183,
        "top": 601,
        "right": 292,
        "bottom": 654,
        "status": "readable",
    }

    PROJECTION_INTERVIEW._advance(
        state, "element_content", "$41,004", contract=12,
    )
    PROJECTION_INTERVIEW._advance(
        state,
        "relationship_endpoint_specificity",
        "one_precise_element_requires_context",
        contract=12,
    )
    selector_claim = PROJECTION_INTERVIEW._endpoint_evidence_claim(state)
    assert selector_claim is not None
    state["current"]["endpoint_crop_evidence"] = {
        **selector_claim,
        "source_sha256": "6" * 64,
        "source_pixel_size": [1000, 1000],
        "pixel_bounds": [183, 601, 292, 654],
        "crop_path": PROJECTION_INTERVIEW._endpoint_evidence_relative_path(
            selector_claim,
        ),
        "crop_sha256": "7" * 64,
        "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
    }

    PROJECTION_INTERVIEW._advance(
        state,
        "element_content_crop_verdict",
        "contains_claimed_content",
        contract=12,
    )

    assert state["stage"] == "endpoint_context_left"
    assert state["current"]["capture_scope"] == "relationship_endpoint_context"
    assert state["current"]["selector_region"] == [183, 601, 292, 654]
    assert state["elements"] == []

    for field, value in (
        ("endpoint_context_left", 183),
        ("endpoint_context_top", 570),
        ("endpoint_context_right", 305),
        ("endpoint_context_bottom", 654),
    ):
        PROJECTION_INTERVIEW._advance(state, field, value, contract=12)
    context_claim = PROJECTION_INTERVIEW._endpoint_evidence_claim(state)
    assert context_claim is not None
    state["current"]["endpoint_crop_evidence"] = {
        **context_claim,
        "source_sha256": "6" * 64,
        "source_pixel_size": [1000, 1000],
        "pixel_bounds": [183, 570, 305, 654],
        "crop_path": PROJECTION_INTERVIEW._endpoint_evidence_relative_path(
            context_claim,
        ),
        "crop_sha256": "8" * 64,
        "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
    }

    PROJECTION_INTERVIEW._advance(
        state,
        "endpoint_context_crop_verdict",
        "contains_claimed_content",
        contract=12,
    )

    assert state["stage"] == "element_relationship_obligation"
    endpoint = state["elements"][0]
    assert endpoint["region"] == [183, 601, 292, 654]
    assert endpoint["content"] == "$41,004"
    assert endpoint["endpoint_verification"]["selector_region"] == [
        183, 601, 292, 654,
    ]
    assert endpoint["endpoint_verification"]["evidence"][
        "normalized_bounds"
    ] == [183, 570, 305, 654]
    assert endpoint["endpoint_verification"]["selector_evidence"][
        "normalized_bounds"
    ] == [183, 601, 292, 654]

    PROJECTION_INTERVIEW._advance(
        state, "element_relationship_obligation", "no", contract=12,
    )
    assert state["stage"] == "relationship_target_x"
    assert state["current"] == {"kind": "visible arrow"}


def test_selector_context_activation_replaces_pending_overbroad_crop_question() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["endpoint_crop_verification_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "element_content_crop_verdict"
    state["current"] = {
        "capture_scope": "relationship_endpoint",
        "return_stage": "relationship_target_x",
        "kind": "dashboard section",
        "left": 172,
        "top": 516,
        "right": 840,
        "bottom": 654,
        "status": "readable",
        "content": "Period Summary with several independent fields",
    }
    claim = PROJECTION_INTERVIEW._endpoint_evidence_claim(state)
    assert claim is not None
    state["current"]["endpoint_crop_evidence"] = {
        **claim,
        "source_sha256": "6" * 64,
        "source_pixel_size": [1000, 1000],
        "pixel_bounds": [172, 516, 840, 654],
        "crop_path": PROJECTION_INTERVIEW._endpoint_evidence_relative_path(
            claim,
        ),
        "crop_sha256": "7" * 64,
        "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
    }
    pending = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )

    event = PROJECTION_INTERVIEW._endpoint_selector_context_activation(
        state, pending, contract=12,
    )
    PROJECTION_INTERVIEW._apply_endpoint_selector_context_activation(
        state, event,
    )

    assert event["pending_scope_recovery"] == {
        "action": "replace_crop_question_with_specificity_question",
        "abandoned_question_id": "element_content_crop_verdict",
    }
    assert state["endpoint_selector_context_enabled"] is True
    assert state["stage"] == "relationship_endpoint_specificity"


def test_identity_context_activation_recovers_a_supported_text_only_selector() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "element_relationship_obligation"
    state["relationship_draft"] = {"kind": "visible arrow"}
    selector_evidence = {
        "candidate_id": "element-000001",
        "normalized_bounds": [183, 611, 268, 642],
        "claimed_content": "$41,004",
    }
    state["elements"] = [{
        "id": "element-000001",
        "kind": "current pay-period earned-to-date monetary value",
        "region": [183, 611, 268, 642],
        "status": "readable",
        "content": "$41,004",
        "gap_reason": "",
        "capture_scope": "relationship_endpoint",
        "endpoint_verification": {
            "verdict": "supported",
            "claimed_content": "$41,004",
            "evidence": selector_evidence,
        },
    }]
    state["current"] = {
        "element_id": "element-000001",
        "return_stage": "relationship_target_x",
    }
    pending = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )

    event = PROJECTION_INTERVIEW._endpoint_identity_context_choice_activation(
        state, pending, contract=12,
    )
    PROJECTION_INTERVIEW._apply_endpoint_identity_context_choice_activation(
        state, event,
    )

    assert event["pending_identity_recovery"]["abandoned_question_id"] == (
        "element_relationship_obligation"
    )
    assert state["elements"][0]["status"] == "gap"
    assert state["elements"][0]["endpoint_verification"]["verdict"] == (
        "requires_visible_context"
    )
    assert state["stage"] == "endpoint_context_left"
    assert state["current"]["selector_region"] == [183, 611, 268, 642]
    assert state["current"]["selector_evidence"] == selector_evidence


def test_identity_context_decision_is_code_controlled() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["endpoint_identity_context_choice_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "relationship_endpoint_specificity"
    state["current"] = {
        "kind": "current pay-period earned-to-date monetary value",
        "left": 183,
        "top": 611,
        "right": 268,
        "bottom": 642,
        "content": "$41,004",
    }

    question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )

    assert question["choices"] == [
        "one_precise_self_identifying_element",
        "one_precise_element_requires_context",
        "multiple_independent_visible_elements",
    ]


def test_required_recorded_participant_must_be_crop_verified_before_reuse() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["existing_participant_crop_verification_enabled"] = True
    state["required_participant_replacement_identity_enabled"] = True
    state["required_participant_content_identity_separation_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "obligation_resolution"
    state["elements"] = [{
        "id": "element-000001",
        "kind": "dashboard metric",
        "region": [600, 300, 650, 350],
        "status": "readable",
        "content": "$20.16 — Avg revenue / visitor",
        "gap_reason": "",
        "capture_scope": "region-r02-c03",
        "scan_region_id": "region-r02-c03",
    }, {
        "id": "element-000002",
        "kind": "annotation",
        "region": [700, 200, 900, 290],
        "status": "readable",
        "content": "The annotation points to the average metric.",
        "gap_reason": "",
        "capture_scope": "region-r01-c04",
        "scan_region_id": "region-r01-c04",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000001",
        "element_id": "element-000001",
        "status": "pending",
        "resolution": None,
        "relationship_id": None,
    }]

    claim = PROJECTION_INTERVIEW._endpoint_evidence_claim(state)
    assert claim == {
        "candidate_id": "element-000001",
        "normalized_bounds": [600, 300, 650, 350],
        "claimed_content": "$20.16 — Avg revenue / visitor",
        "verification_scope": "required_recorded_participant",
    }
    state["current"]["endpoint_crop_evidence"] = {
        **claim,
        "source_sha256": "6" * 64,
        "source_pixel_size": [1000, 1000],
        "pixel_bounds": [600, 300, 650, 350],
        "crop_path": "endpoint-evidence/element-000001-required-recorded-participant.png",
        "crop_sha256": "7" * 64,
        "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
    }
    question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    assert question["id"] == "required_participant_crop_verdict"
    assert question["choices"] == [
        "contains_claimed_content",
        "does_not_contain_claimed_content",
        "unreadable",
    ]

    PROJECTION_INTERVIEW._advance(
        state,
        "required_participant_crop_verdict",
        "does_not_contain_claimed_content",
        contract=12,
    )
    invalidation = state["element_supersession_pending"]["event"]
    assert invalidation["previous_element"]["content"] == (
        "$20.16 — Avg revenue / visitor"
    )
    assert invalidation["replacement_element"]["status"] == "gap"
    assert invalidation["replacement_element"]["content"] == ""
    PROJECTION_INTERVIEW._apply_element_supersession(state, invalidation)
    assert state["stage"] == "element_kind"
    assert state["current"] == {
        "capture_scope": "required_participant_replacement",
        "return_stage": "obligation_resolution",
        "superseded_element_id": "element-000001",
        "required_identity_claim": "$20.16 — Avg revenue / visitor",
    }

    for field_id, value in (
        ("element_kind", "dashboard metric"),
        ("element_left", 600),
        ("element_top", 300),
        ("element_right", 700),
        ("element_bottom", 360),
        ("element_status", "readable"),
        ("element_content", "$20.16 — Avg revenue / transaction"),
    ):
        PROJECTION_INTERVIEW._advance(state, field_id, value, contract=12)
    replacement_claim = PROJECTION_INTERVIEW._endpoint_evidence_claim(state)
    state["current"]["endpoint_crop_evidence"] = {
        **replacement_claim,
        "source_sha256": "6" * 64,
        "source_pixel_size": [1000, 1000],
        "pixel_bounds": [600, 300, 700, 360],
        "crop_path": "endpoint-evidence/element-000001-required-participant-replacement.png",
        "crop_sha256": "8" * 64,
        "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
    }
    crop_question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    crop_prompt = PROJECTION_INTERVIEW._prompt(crop_question, state)
    assert "Judge only that proposed content here" in crop_question["prompt"]
    assert "Preserved required identity" not in crop_prompt
    PROJECTION_INTERVIEW._advance(
        state,
        "element_content_crop_verdict",
        "contains_claimed_content",
        contract=12,
    )
    identity_question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    assert identity_question["id"] == (
        "required_participant_replacement_identity_verdict"
    )
    assert identity_question["choices"] == [
        "same_required_source_unit", "different_source_unit",
    ]
    assert identity_question["required_identity_comparison"] == {
        "required_claim": "$20.16 — Avg revenue / visitor",
        "proposed_kind": "dashboard metric",
        "proposed_content": "$20.16 — Avg revenue / transaction",
        "proposed_bounds": [600, 300, 700, 360],
    }
    PROJECTION_INTERVIEW._advance(
        state,
        "required_participant_replacement_identity_verdict",
        "same_required_source_unit",
        contract=12,
    )
    correction = state["element_supersession_pending"]["event"]
    assert correction["previous_element"]["status"] == "gap"
    assert correction["replacement_element"]["content"] == (
        "$20.16 — Avg revenue / transaction"
    )
    assert correction["replacement_element"]["endpoint_verification"]["verdict"] == (
        "supported"
    )
    assert correction["replacement_element"]["endpoint_verification"][
        "identity_continuity"
    ] == {
        "verdict": "same_required_source_unit",
        "required_claim": "$20.16 — Avg revenue / visitor",
    }
    PROJECTION_INTERVIEW._apply_element_supersession(state, correction)

    assert state["elements"][0]["id"] == "element-000001"
    assert state["elements"][0]["status"] == "readable"
    assert state["elements"][0]["content"] == (
        "$20.16 — Avg revenue / transaction"
    )
    assert state["relationship_obligations"][0]["status"] == "pending"
    assert PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )["id"] == "obligation_resolution"


def test_context_dependent_claim_cannot_be_supported_by_tight_crop_alone() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["existing_participant_crop_verification_enabled"] = True
    state["contextual_endpoint_verification_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "obligation_resolution"
    state["elements"] = [{
        "id": "element-000001",
        "kind": "chart data point",
        "region": [725, 449, 730, 454],
        "status": "readable",
        "content": "June monthly line-chart data point",
        "gap_reason": "",
        "capture_scope": "region-r02-c03",
        "scan_region_id": "region-r02-c03",
        "endpoint_verification": {
            "verdict": "supported",
            "claimed_content": "June monthly line-chart data point",
            "evidence": {"crop_sha256": "7" * 64},
        },
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000001",
        "element_id": "element-000001",
        "status": "pending",
        "resolution": None,
        "relationship_id": None,
    }]
    claim = PROJECTION_INTERVIEW._endpoint_evidence_claim(state)
    state["current"]["endpoint_crop_evidence"] = {
        **claim,
        "source_sha256": "6" * 64,
        "source_pixel_size": [1778, 1623],
        "pixel_bounds": [1289, 728, 1298, 737],
        "crop_path": (
            "endpoint-evidence/element-000001-required-recorded-participant.png"
        ),
        "crop_sha256": "8" * 64,
        "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
    }

    question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    assert "requires_visible_context" in question["choices"]
    assert "crop alone" in question["prompt"]

    PROJECTION_INTERVIEW._advance(
        state,
        "required_participant_crop_verdict",
        "requires_visible_context",
        contract=12,
    )
    replacement = state["element_supersession_pending"]["event"][
        "replacement_element"
    ]
    assert replacement["status"] == "gap"
    assert replacement["content"] == ""
    assert "context outside" in replacement["gap_reason"]
    assert replacement["endpoint_verification"]["verdict"] == (
        "requires_visible_context"
    )


def test_different_required_participant_replacement_is_rejected_by_enum() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["required_participant_replacement_identity_enabled"] = True
    state["stage"] = "required_participant_replacement_identity_verdict"
    original_gap = {
        "id": "element-000055", "kind": "metric value",
        "region": [185, 135, 267, 153], "status": "gap", "content": "",
        "gap_reason": "The claimed content is not visible inside the claimed bounds.",
        "endpoint_verification": {
            "verdict": "does_not_contain_claimed_content",
            "claimed_content": "364 transactions today",
            "evidence": {"crop_sha256": "7" * 64},
        },
    }
    state["elements"] = [original_gap]
    state["relationship_obligations"] = [{
        "id": "obligation-000053", "element_id": "element-000055",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    state["current"] = {
        "capture_scope": "required_participant_replacement",
        "return_stage": "obligation_resolution",
        "superseded_element_id": "element-000055",
        "required_identity_claim": "364 transactions today",
        "kind": "metric label", "left": 184, "top": 102,
        "right": 280, "bottom": 164, "status": "readable",
        "content": "NET REVENUE TODAY: $8,100; Operator Net",
        "endpoint_crop_evidence": {
            "candidate_id": "element-000055",
            "source_sha256": "6" * 64,
            "source_pixel_size": [1000, 1000],
            "normalized_bounds": [184, 102, 280, 164],
            "pixel_bounds": [184, 102, 280, 164],
            "crop_path": (
                "endpoint-evidence/element-000055-"
                "required-participant-replacement.png"
            ),
            "crop_sha256": "8" * 64,
            "claimed_content": "NET REVENUE TODAY: $8,100; Operator Net",
            "verification_scope": "required_participant_replacement",
            "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
        },
        "endpoint_verification": {"verdict": "supported"},
    }

    PROJECTION_INTERVIEW._advance(
        state,
        "required_participant_replacement_identity_verdict",
        "different_source_unit",
        contract=12,
    )

    assert state["elements"] == [original_gap]
    assert state["relationship_obligations"][0]["status"] == "pending"
    assert state["stage"] == "element_kind"
    assert state["current"]["required_identity_claim"] == "364 transactions today"
    assert state["current"]["last_identity_rejection"]["proposed_content"] == (
        "NET REVENUE TODAY: $8,100; Operator Net"
    )
    assert "content" not in state["current"]


def test_different_required_participant_replacement_terminalizes_as_gap() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=13)
    state["required_participant_replacement_identity_enabled"] = True
    state["required_participant_identity_mismatch_terminalization_enabled"] = True
    state["stage"] = "required_participant_replacement_identity_verdict"
    original_gap = {
        "id": "element-000020", "kind": "red annotation text box",
        "region": [1, 294, 159, 364], "status": "gap", "content": "",
        "gap_reason": "The claimed content is not visible inside the claimed source bounds.",
        "endpoint_verification": {
            "verdict": "does_not_contain_claimed_content",
            "claimed_content": "The sum of Column AE for all locations for the current day.",
            "evidence": {"crop_sha256": "7" * 64},
        },
    }
    state["elements"] = [original_gap]
    state["relationship_obligations"] = [{
        "id": "obligation-000020", "element_id": "element-000020",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    state["current"] = {
        "capture_scope": "required_participant_replacement",
        "return_stage": "obligation_resolution",
        "superseded_element_id": "element-000020",
        "required_identity_claim": (
            "The sum of Column AE for all locations for the current day."
        ),
        "kind": "red annotation text box", "left": 0, "top": 287,
        "right": 160, "bottom": 359, "status": "readable",
        "content": "The sum of Column AF for all locations for the current day.",
        "endpoint_crop_evidence": {
            "candidate_id": "element-000020",
            "source_sha256": "6" * 64,
            "source_pixel_size": [1778, 1623],
            "normalized_bounds": [0, 287, 160, 359],
            "pixel_bounds": [0, 465, 285, 583],
            "crop_path": "endpoint-evidence/element-000020-replacement.png",
            "crop_sha256": "8" * 64,
            "claimed_content": (
                "The sum of Column AF for all locations for the current day."
            ),
            "verification_scope": "required_participant_replacement",
            "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
        },
        "endpoint_verification": {"verdict": "supported"},
    }

    PROJECTION_INTERVIEW._advance(
        state,
        "required_participant_replacement_identity_verdict",
        "different_source_unit",
        contract=13,
    )

    obligation = state["relationship_obligations"][0]
    assert obligation["status"] == "resolved"
    assert obligation["resolution"] == "gap"
    relationship = state["relationships"][0]
    assert relationship["status"] == "gap"
    assert relationship["participant_id"] == "element-000020"
    assert "Column AE" in relationship["gap_reason"]
    assert "Column AF" in relationship["gap_reason"]
    assert state["stage"] != "element_kind"
    assert state["current"] == {}


def test_pending_legacy_identity_mismatch_has_append_only_terminalization() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=13)
    state["stage"] = "element_left"
    state["elements"] = [{
        "id": "element-000020", "kind": "red annotation text box",
        "region": [1, 294, 159, 364], "status": "gap", "content": "",
        "gap_reason": "The claimed content is not visible inside the claimed source bounds.",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000020", "element_id": "element-000020",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    state["current"] = {
        "capture_scope": "required_participant_replacement",
        "return_stage": "obligation_resolution",
        "superseded_element_id": "element-000020",
        "required_identity_claim": "The sum of Column AE for all locations.",
        "kind": "red annotation text box",
        "last_identity_rejection": {
            "verdict": "different_source_unit",
            "required_claim": "The sum of Column AE for all locations.",
            "proposed_kind": "red annotation text box",
            "proposed_content": "The sum of Column AF for all locations.",
            "proposed_bounds": [0, 287, 160, 359],
            "endpoint_crop_evidence": {"crop_sha256": "8" * 64},
        },
    }
    pending = {
        "id": "element_left", "type": "integer", "required": True,
        "minimum": 0, "maximum": 999,
        "prompt": "What is the element's normalized left coordinate?",
        "context": {"intake_purpose": REAL_PURPOSE},
    }

    activation = (
        PROJECTION_INTERVIEW
        ._required_participant_identity_mismatch_terminalization_activation(
            state, pending, contract=13,
        )
    )
    assert activation["pending_recovery"]["abandoned_question_id"] == "element_left"

    PROJECTION_INTERVIEW._apply_required_participant_identity_mismatch_terminalization(
        state, activation,
    )

    assert state["required_participant_identity_mismatch_terminalization_enabled"] is True
    assert state["relationship_obligations"][0]["resolution"] == "gap"
    assert state["relationships"][0]["status"] == "gap"
    assert state["current"] == {}


def test_unverified_live_replacement_is_reopened_append_only() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    restored = {
        "id": "element-000055", "kind": "metric value",
        "region": [185, 135, 267, 153], "status": "gap", "content": "",
        "gap_reason": "The claimed content is not visible inside the claimed bounds.",
        "endpoint_verification": {
            "verdict": "does_not_contain_claimed_content",
            "claimed_content": "364 transactions today",
            "evidence": {"crop_sha256": "7" * 64},
        },
    }
    false_replacement = {
        **restored, "kind": "metric label", "region": [184, 102, 280, 164],
        "status": "readable", "content": "NET REVENUE TODAY: $8,100",
        "gap_reason": "",
        "endpoint_verification": {
            "verdict": "supported",
            "claimed_content": "NET REVENUE TODAY: $8,100",
            "evidence": {"crop_sha256": "8" * 64},
        },
    }
    relationship = {
        "id": "relationship-000047", "kind": "annotation arrow",
        "from_id": "element-000001", "to_id": "element-000055",
        "status": "readable", "description": "Column AF points to $8,100.",
        "gap_reason": "", "visual_verification": "supported",
        "verified_obligation_id": "obligation-000053",
        "verified_element_id": "element-000055",
    }
    obligation = {
        "id": "obligation-000053", "element_id": "element-000055",
        "status": "resolved", "resolution": "relationship",
        "relationship_id": "relationship-000047",
    }
    state["elements"] = [false_replacement]
    state["relationships"] = [relationship]
    state["relationship_obligations"] = [obligation]
    entries = [{
        "event": "element_superseded",
        "element_id": "element-000055",
        "reason": "required_participant_replaced_from_source",
        "previous_element": restored,
        "trigger_candidate": {
            "kind": "metric label", "region": [184, 102, 280, 164],
            "verification_scope": "required_participant_replacement",
        },
        "replacement_element": false_replacement,
    }]

    migration = (
        PROJECTION_INTERVIEW._latest_unverified_replacement_identity_migration(
            state, entries,
        )
    )
    assert migration is not None
    PROJECTION_INTERVIEW._apply_unverified_replacement_identity_migration(
        state, migration,
    )

    assert state["elements"] == [restored]
    assert state["relationships"][0]["resolution_status"] == "invalidated"
    assert state["relationship_obligations"][0]["status"] == "pending"
    assert state["current"] == {
        "capture_scope": "required_participant_replacement",
        "return_stage": "obligation_resolution",
        "superseded_element_id": "element-000055",
        "required_identity_claim": "364 transactions today",
    }
    assert state["stage"] == "element_kind"


def test_context_evidence_keeps_precise_endpoint_bounds_immutable() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["existing_participant_crop_verification_enabled"] = True
    state["contextual_endpoint_verification_enabled"] = True
    state["endpoint_context_evidence_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "obligation_resolution"
    state["elements"] = [{
        "id": "element-000001",
        "kind": "chart data point",
        "region": [725, 449, 730, 454],
        "status": "readable",
        "content": "June monthly line-chart data point",
        "gap_reason": "",
        "capture_scope": "region-r02-c03",
        "scan_region_id": "region-r02-c03",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000001",
        "element_id": "element-000001",
        "status": "pending",
        "resolution": None,
        "relationship_id": None,
    }]
    claim = PROJECTION_INTERVIEW._endpoint_evidence_claim(state)
    state["current"]["endpoint_crop_evidence"] = {
        **claim,
        "source_sha256": "6" * 64,
        "source_pixel_size": [1778, 1623],
        "pixel_bounds": [1289, 728, 1298, 737],
        "crop_path": (
            "endpoint-evidence/element-000001-required-recorded-participant.png"
        ),
        "crop_sha256": "8" * 64,
        "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
    }

    PROJECTION_INTERVIEW._advance(
        state,
        "required_participant_crop_verdict",
        "requires_visible_context",
        contract=12,
    )

    assert state["elements"][0]["status"] == "readable"
    assert state["elements"][0]["region"] == [725, 449, 730, 454]
    assert state["stage"] == "endpoint_context_left"
    assert state["current"]["selector_region"] == [725, 449, 730, 454]

    for field_id, value in (
        ("endpoint_context_left", 700),
        ("endpoint_context_top", 400),
        ("endpoint_context_right", 760),
        ("endpoint_context_bottom", 540),
    ):
        PROJECTION_INTERVIEW._advance(state, field_id, value, contract=12)

    context_claim = PROJECTION_INTERVIEW._endpoint_evidence_claim(state)
    assert context_claim["normalized_bounds"] == [700, 400, 760, 540]
    assert context_claim["verification_scope"] == "required_participant_context"
    state["current"]["endpoint_crop_evidence"] = {
        **context_claim,
        "source_sha256": "6" * 64,
        "source_pixel_size": [1000, 1000],
        "pixel_bounds": [700, 400, 760, 540],
        "crop_path": PROJECTION_INTERVIEW._endpoint_evidence_relative_path(
            context_claim
        ),
        "crop_sha256": "9" * 64,
        "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
    }
    PROJECTION_INTERVIEW._advance(
        state,
        "endpoint_context_crop_verdict",
        "contains_claimed_content",
        contract=12,
    )
    correction = state["element_supersession_pending"]["event"]

    assert correction["replacement_element"]["region"] == [725, 449, 730, 454]
    verification = correction["replacement_element"]["endpoint_verification"]
    assert verification["evidence"]["normalized_bounds"] == [700, 400, 760, 540]
    assert verification["selector_region"] == [725, 449, 730, 454]
    assert verification["claim_scope"] == "selector_with_context_v3"


def test_negative_context_verdict_reopens_required_participant_for_replacement() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["existing_participant_crop_verification_enabled"] = True
    state["contextual_endpoint_verification_enabled"] = True
    state["endpoint_context_evidence_enabled"] = True
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "endpoint_context_crop_verdict"
    state["elements"] = [{
        "id": "element-000041",
        "kind": "annotation",
        "region": [10, 603, 260, 680],
        "status": "readable",
        "content": "The sum of Column: AF for the current pay period.",
        "gap_reason": "",
        "capture_scope": "region-r03-c01",
        "scan_region_id": "region-r03-c01",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000039",
        "element_id": "element-000041",
        "status": "pending",
        "resolution": None,
        "relationship_id": None,
    }]
    state["current"] = {
        "capture_scope": "required_participant_context",
        "element_id": "element-000041",
        "claimed_content": "The sum of Column: AF for the current pay period.",
        "selector_region": [10, 603, 260, 680],
        "context_left": 0,
        "context_top": 525,
        "context_right": 500,
        "context_bottom": 680,
    }
    claim = PROJECTION_INTERVIEW._endpoint_evidence_claim(state)
    state["current"]["endpoint_crop_evidence"] = {
        **claim,
        "source_sha256": "6" * 64,
        "source_pixel_size": [1778, 1623],
        "pixel_bounds": [0, 852, 889, 1104],
        "crop_path": (
            "endpoint-evidence/element-000041-required-participant-context.png"
        ),
        "crop_sha256": "9" * 64,
        "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
    }

    PROJECTION_INTERVIEW._advance(
        state,
        "endpoint_context_crop_verdict",
        "does_not_contain_claimed_content",
        contract=12,
    )

    pending = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    activation = PROJECTION_INTERVIEW._negative_context_replacement_activation(
        state, pending, contract=12,
    )
    assert activation["pending_negative_context_recovery"][
        "abandoned_question_id"
    ] == "endpoint_context_left"
    PROJECTION_INTERVIEW._apply_negative_context_replacement_activation(
        state, activation,
    )

    invalidation = state["element_supersession_pending"]
    assert invalidation["event"]["reason"] == "required_participant_source_rejected"
    assert invalidation["event"]["replacement_element"]["status"] == "gap"
    assert invalidation["event"]["replacement_element"]["region"] == [
        10, 603, 260, 680,
    ]
    assert invalidation["next_current"] == {
        "capture_scope": "required_participant_replacement",
        "return_stage": "obligation_resolution",
        "superseded_element_id": "element-000041",
        "required_identity_claim": (
            "The sum of Column: AF for the current pay period."
        ),
    }
    assert state["stage"] == "element_supersession_pending"


def test_context_verification_migration_reopens_latest_relationship() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["elements"] = [{
        "id": "element-000001",
        "kind": "chart data point",
        "region": [725, 449, 730, 454],
        "status": "readable",
        "content": "June monthly line-chart data point",
        "gap_reason": "",
        "capture_scope": "region-r02-c03",
        "scan_region_id": "region-r02-c03",
        "endpoint_verification": {
            "verdict": "supported",
            "claimed_content": "June monthly line-chart data point",
            "evidence": {"crop_sha256": "7" * 64},
        },
    }]
    state["relationships"] = [{
        "id": "relationship-000001",
        "kind": "annotation linked to chart point",
        "from_id": "element-000002",
        "to_id": "element-000001",
        "status": "readable",
        "description": "The annotation points to the June chart point.",
        "gap_reason": "",
        "visual_verification": "supported",
        "verified_obligation_id": "obligation-000001",
        "verified_element_id": "element-000001",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000001",
        "element_id": "element-000001",
        "status": "resolved",
        "resolution": "relationship",
        "relationship_id": "relationship-000001",
    }]

    migration = (
        PROJECTION_INTERVIEW._latest_context_unassessed_participant_migration(
            state,
        )
    )
    assert migration["replacement_obligation"]["status"] == "pending"
    assert migration["replacement_relationship"]["resolution_status"] == (
        "invalidated"
    )
    PROJECTION_INTERVIEW._apply_latest_unverified_required_participant_migration(
        state, migration,
    )
    assert state["relationship_obligations"][0]["status"] == "pending"
    assert state["stage"] == "obligation_resolution"


def test_contract_twelve_reopens_latest_relationship_that_bypassed_crop_gate() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "obligation_resolution"
    state["elements"] = [{
        "id": "element-000001", "kind": "metric",
        "region": [600, 300, 650, 350], "status": "readable",
        "content": "$20.16 — Avg revenue / visitor", "gap_reason": "",
        "capture_scope": "region-r02-c03",
    }, {
        "id": "element-000002", "kind": "annotation",
        "region": [700, 200, 900, 290], "status": "readable",
        "content": "Formula annotation", "gap_reason": "",
        "capture_scope": "region-r01-c04",
    }]
    state["relationships"] = [{
        "id": "relationship-000001", "kind": "visible arrow",
        "from_id": "element-000002", "to_id": "element-000001",
        "status": "readable", "description": "The formula points to $20.16.",
        "gap_reason": "", "visual_verification": "supported",
        "verified_obligation_id": "obligation-000001",
        "verified_element_id": "element-000001",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000001", "element_id": "element-000001",
        "status": "resolved", "resolution": "relationship",
        "relationship_id": "relationship-000001",
    }]

    event = (
        PROJECTION_INTERVIEW._latest_unverified_required_participant_migration(
            state
        )
    )
    assert event is not None
    PROJECTION_INTERVIEW._apply_latest_unverified_required_participant_migration(
        state, event,
    )

    assert state["relationships"][0]["status"] == "gap"
    assert state["relationships"][0]["resolution_status"] == "invalidated"
    assert state["relationship_obligations"][0] == {
        "id": "obligation-000001", "element_id": "element-000001",
        "status": "pending", "resolution": None, "relationship_id": None,
    }
    assert state["stage"] == "obligation_resolution"


def test_required_participant_recapture_receives_exact_rejected_crop_and_full_source(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "attempt"
    crop = attempt / "endpoint-evidence" / (
        "element-000001-required-participant-replacement.png"
    )
    crop.parent.mkdir(parents=True)
    crop.write_bytes(b"exact rejected crop")
    source = tmp_path / "source.png"
    source.write_bytes(b"full frozen source")
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["stage"] = "element_kind"
    state["elements"] = [{
        "id": "element-000001", "kind": "metric",
        "region": [600, 300, 650, 350], "status": "gap", "content": "",
        "gap_reason": "The replacement claim is outside the exact crop.",
        "capture_scope": "region-r02-c03",
        "endpoint_verification": {
            "verdict": "does_not_contain_claimed_content",
            "claimed_content": "18.2%",
            "evidence": {
                "candidate_id": "element-000001",
                "source_sha256": "6" * 64,
                "source_pixel_size": [1000, 1000],
                "normalized_bounds": [600, 300, 650, 350],
                "pixel_bounds": [600, 300, 650, 350],
                "crop_path": (
                    "endpoint-evidence/element-000001-"
                    "required-participant-replacement.png"
                ),
                "crop_sha256": PROJECTION_INTERVIEW._digest(
                    b"exact rejected crop"
                ),
                "claimed_content": "18.2%",
                "verification_scope": "required_participant_replacement",
                "adapter": PROJECTION_INTERVIEW.ENDPOINT_CROP_EVIDENCE_ADAPTER,
            },
        },
    }]
    state["current"] = {
        "capture_scope": "required_participant_replacement",
        "return_stage": "obligation_resolution",
        "superseded_element_id": "element-000001",
        "required_identity_claim": "18.2%",
    }

    attachments = (
        PROJECTION_INTERVIEW.required_participant_replacement_attachments(
            attempt,
            state,
            source_path=source,
            source_sha256="6" * 64,
        )
    )
    assert attachments == (crop, source)
    question = PROJECTION_INTERVIEW._question(
        state, purpose=REAL_PURPOSE, contract=12,
    )
    prompt = PROJECTION_INTERVIEW._prompt(question, state)
    assert "first attached image shows why the old bounds were rejected" in prompt
    assert "second attached image is the complete frozen source" in prompt
    assert 'Preserved required identity: "18.2%"' in prompt
    first_claim = {
        "candidate_id": "element-000001",
        "normalized_bounds": [600, 300, 650, 350],
        "claimed_content": "18.2%",
        "verification_scope": "required_participant_replacement",
    }
    corrected_claim = {
        **first_claim,
        "normalized_bounds": [590, 290, 700, 370],
        "claimed_content": "Avg revenue / transaction: $20.16",
    }
    assert PROJECTION_INTERVIEW._endpoint_evidence_relative_path(
        first_claim
    ) != PROJECTION_INTERVIEW._endpoint_evidence_relative_path(corrected_claim)


def test_historical_false_endpoint_becomes_gap_and_only_required_claim_reopens() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["scan_region_index"] = len(state["scan_regions"])
    state["stage"] = "obligation_resolution"
    state["elements"] = [{
        "id": "element-000027", "kind": "annotation", "region": [312, 265, 413, 308],
        "status": "readable", "content": "Sum of Column X divided by Column W",
        "gap_reason": "", "capture_scope": "region-r02-c02",
    }, {
        "id": "element-000061", "kind": "metric", "region": [363, 416, 407, 442],
        "status": "readable", "content": "$22.25 avg / transaction",
        "gap_reason": "", "capture_scope": "relationship_endpoint",
    }]
    state["relationships"] = [{
        "id": "relationship-000023", "kind": "visible arrow",
        "from_id": "element-000027", "to_id": "element-000061",
        "status": "readable", "description": "The annotation points to $22.25.",
        "gap_reason": "", "visual_verification": "supported",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000027", "element_id": "element-000027",
        "status": "resolved", "resolution": "relationship",
        "relationship_id": "relationship-000023",
    }, {
        "id": "obligation-000059", "element_id": "element-000061",
        "status": "resolved", "resolution": "relationship",
        "relationship_id": "relationship-000023",
    }]
    reason = "Independent crop evidence does not contain the claimed content."

    event = PROJECTION_INTERVIEW._historical_endpoint_grounding_invalidation(
        state,
        element_id="element-000061",
        relationship_id="relationship-000023",
        reason=reason,
    )
    PROJECTION_INTERVIEW._apply_historical_endpoint_grounding_invalidation(
        state, event,
    )

    assert state["elements"][1]["status"] == "gap"
    assert state["elements"][1]["content"] == ""
    assert state["relationships"][0]["status"] == "gap"
    assert state["relationships"][0]["description"] == ""
    assert state["relationship_obligations"][0]["status"] == "pending"
    assert state["relationship_obligations"][1]["resolution"] == (
        "invalidated_endpoint"
    )
    assert PROJECTION_INTERVIEW._pending_obligation(state)["id"] == (
        "obligation-000027"
    )


def test_relationship_point_binding_excludes_rejected_gap_endpoint() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["rejected_endpoint_reuse_blocked_enabled"] = True
    state["elements"] = [{
        "id": "element-000027", "kind": "annotation", "region": [312, 265, 413, 308],
        "status": "readable", "content": "Sum of Column X divided by Column W",
        "gap_reason": "", "capture_scope": "region-r02-c02",
    }, {
        "id": "element-000062", "kind": "metric", "region": [363, 326, 407, 350],
        "status": "gap", "content": "",
        "gap_reason": "The claimed content is not visible inside the claimed source bounds.",
        "capture_scope": "relationship_endpoint",
        "endpoint_verification": {
            "verdict": "does_not_contain_claimed_content",
        },
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000027", "element_id": "element-000027",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    state["current"] = {
        "kind": "directional annotation-to-metric relationship",
        "role": "origin",
        "origin_id": "element-000027",
        "origin_point": [362, 286],
        "target_x": 380,
    }
    state["stage"] = "relationship_target_y"

    PROJECTION_INTERVIEW._advance(
        state, "relationship_target_y", 338, contract=12,
    )

    assert state["stage"] == "relationship_binding_resolution"
    assert state["current"]["binding_issue"] == {
        "participant": "target",
        "point": [380, 338],
        "matching_element_ids": [],
        "reason": "no_unique_recorded_element",
    }


def test_relationship_point_binding_excludes_region_gap_participant() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["rejected_endpoint_reuse_blocked_enabled"] = True
    state["unreadable_participant_reuse_blocked_enabled"] = True
    state["elements"] = [{
        "id": "element-000042", "kind": "metric", "region": [357, 590, 419, 616],
        "status": "readable", "content": "PROJECTED CLOSE: $48,000",
        "gap_reason": "", "capture_scope": "region-r03-c02",
    }, {
        "id": "element-000028", "kind": "annotation", "region": [376, 465, 550, 568],
        "status": "gap", "content": "",
        "gap_reason": "The description is clipped at the region edge.",
        "capture_scope": "region-r03-c02",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000040", "element_id": "element-000042",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    state["current"] = {
        "kind": "annotation-to-metric relationship",
        "role": "target",
        "target_id": "element-000042",
        "target_point": [388, 603],
        "origin_x": 465,
    }
    state["stage"] = "relationship_origin_y"

    PROJECTION_INTERVIEW._advance(
        state, "relationship_origin_y", 530, contract=12,
    )

    assert state["stage"] == "relationship_binding_resolution"
    assert state["current"]["binding_issue"] == {
        "participant": "origin",
        "point": [465, 530],
        "matching_element_ids": [],
        "reason": "no_unique_recorded_element",
    }


def test_readable_relationship_with_rejected_endpoint_is_reopened_append_only() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["elements"] = [{
        "id": "element-000027", "kind": "annotation", "region": [312, 265, 413, 308],
        "status": "readable", "content": "Sum of Column X divided by Column W",
        "gap_reason": "", "capture_scope": "region-r02-c02",
    }, {
        "id": "element-000062", "kind": "metric", "region": [363, 326, 407, 350],
        "status": "gap", "content": "", "gap_reason": "Rejected by exact crop.",
        "capture_scope": "relationship_endpoint",
        "endpoint_verification": {
            "verdict": "does_not_contain_claimed_content",
        },
    }]
    state["relationships"] = [{
        "id": "relationship-000024", "kind": "visible arrow",
        "from_id": "element-000027", "to_id": "element-000062",
        "status": "readable", "description": "Annotation points to metric.",
        "gap_reason": "", "visual_verification": "supported",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000027", "element_id": "element-000027",
        "status": "resolved", "resolution": "relationship",
        "relationship_id": "relationship-000024",
    }]

    event = (
        PROJECTION_INTERVIEW._readable_relationship_rejected_endpoint_migration(
            state,
        )
    )
    PROJECTION_INTERVIEW._apply_readable_relationship_rejected_endpoint_migration(
        state, event,
    )

    assert state["relationships"][0]["status"] == "gap"
    assert state["relationships"][0]["description"] == ""
    assert state["relationships"][0]["rejected_endpoint_invalidation"][
        "element_ids"
    ] == ["element-000062"]
    assert state["relationship_obligations"][0] == {
        "id": "obligation-000027", "element_id": "element-000027",
        "status": "pending", "resolution": None, "relationship_id": None,
    }


def test_legacy_rejected_endpoint_invalidation_keeps_original_contract() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["elements"] = [{
        "id": "element-000027", "kind": "annotation", "region": [312, 265, 413, 308],
        "status": "readable", "content": "Sum of Column X divided by Column W",
        "gap_reason": "", "capture_scope": "region-r02-c02",
    }, {
        "id": "element-000062", "kind": "metric", "region": [363, 326, 407, 350],
        "status": "gap", "content": "", "gap_reason": "Rejected by exact crop.",
        "capture_scope": "relationship_endpoint",
        "endpoint_verification": {
            "verdict": "does_not_contain_claimed_content",
        },
    }]
    state["relationships"] = [{
        "id": "relationship-000024", "kind": "visible arrow",
        "from_id": "element-000027", "to_id": "element-000062",
        "status": "readable", "description": "Annotation points to metric.",
        "gap_reason": "", "visual_verification": "supported",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000027", "element_id": "element-000027",
        "status": "resolved", "resolution": "relationship",
        "relationship_id": "relationship-000024",
    }]

    event = PROJECTION_INTERVIEW._readable_relationship_rejected_endpoint_migration(
        state, eligibility_contract="rejected_endpoint_v1",
    )

    assert event is not None
    assert "eligibility_contract" not in event
    assert event["replacement_relationship"]["gap_reason"] == (
        "A readable relationship cannot reuse an endpoint rejected by exact source evidence."
    )


def test_readable_relationship_with_region_gap_participant_is_reopened() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["elements"] = [{
        "id": "element-000028", "kind": "annotation", "region": [376, 465, 550, 568],
        "status": "gap", "content": "",
        "gap_reason": "The description is clipped at the region edge.",
        "capture_scope": "region-r03-c02",
    }, {
        "id": "element-000042", "kind": "metric", "region": [357, 590, 419, 616],
        "status": "readable", "content": "PROJECTED CLOSE: $48,000",
        "gap_reason": "", "capture_scope": "region-r03-c02",
    }]
    state["relationships"] = [{
        "id": "relationship-000034", "kind": "visible arrow",
        "from_id": "element-000028", "to_id": "element-000042",
        "status": "readable", "description": "Annotation explains projected close.",
        "gap_reason": "", "visual_verification": "supported",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000040", "element_id": "element-000042",
        "status": "resolved", "resolution": "relationship",
        "relationship_id": "relationship-000034",
    }]

    event = (
        PROJECTION_INTERVIEW._readable_relationship_rejected_endpoint_migration(
            state,
        )
    )

    assert event is not None
    assert event["eligibility_contract"] == "unreadable_participant_v2"
    PROJECTION_INTERVIEW._apply_readable_relationship_rejected_endpoint_migration(
        state, event,
    )
    assert state["relationships"][0]["status"] == "gap"
    assert state["relationship_obligations"][0]["status"] == "pending"


def test_v1_relationship_completion_replays_before_v2_gap_enforcement() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["rejected_endpoint_reuse_blocked_enabled"] = True
    state["elements"] = [{
        "id": "element-000028", "kind": "annotation", "region": [376, 465, 550, 568],
        "status": "gap", "content": "", "gap_reason": "Clipped at the edge.",
        "capture_scope": "region-r03-c02",
    }, {
        "id": "element-000042", "kind": "metric", "region": [357, 590, 419, 616],
        "status": "readable", "content": "PROJECTED CLOSE: $48,000",
        "gap_reason": "", "capture_scope": "region-r03-c02",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000040", "element_id": "element-000042",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    state["current"] = {
        "kind": "visible arrow", "origin_id": "element-000028",
        "target_id": "element-000042", "status": "readable",
        "description": "Annotation explains projected close.",
        "visual_verification": "supported",
    }

    PROJECTION_INTERVIEW._finish_relationship(
        state, "description", "Annotation explains projected close.", contract=12,
    )

    assert state["relationships"][0]["status"] == "readable"
    state["unreadable_participant_reuse_blocked_enabled"] = True
    state["relationship_obligations"][0].update({
        "status": "pending", "resolution": None, "relationship_id": None,
    })
    state["current"] = {
        "kind": "visible arrow", "origin_id": "element-000028",
        "target_id": "element-000042", "status": "readable",
        "description": "Annotation explains projected close.",
        "visual_verification": "supported",
    }
    PROJECTION_INTERVIEW._finish_relationship(
        state, "description", "Annotation explains projected close.", contract=12,
    )
    assert len(state["relationships"]) == 1
    assert state["stage"] == "relationship_binding_resolution"
    assert state["current"]["binding_issue"]["participant"] == "origin"


def test_unreadable_required_participant_recovery_recaptures_that_participant() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=13)
    state["unreadable_participant_reuse_blocked_enabled"] = True
    state["failed_participant_recovery_enabled"] = True
    state["elements"] = [{
        "id": "element-000031", "kind": "annotation", "region": [694, 385, 800, 428],
        "status": "gap", "content": "", "gap_reason": "Clipped by region crop.",
        "capture_scope": "region-r02-c03",
    }, {
        "id": "element-000032", "kind": "metric", "region": [477, 349, 650, 405],
        "status": "readable", "content": "Capture rate: 18.2%.", "gap_reason": "",
        "capture_scope": "region-r02-c03",
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000030", "element_id": "element-000031",
        "status": "pending", "resolution": None, "relationship_id": None,
    }]
    state["current"] = {
        "kind": "annotation arrow", "origin_id": "element-000031",
        "target_id": "element-000032", "origin_point": [750, 405],
        "target_point": [625, 370], "visual_verification": "supported",
        "status": "readable",
    }

    PROJECTION_INTERVIEW._finish_relationship(
        state, "description", "The annotation points to Capture rate.", contract=13,
    )
    PROJECTION_INTERVIEW._advance(
        state, "relationship_binding_resolution", "record_visible_endpoint",
        contract=13,
    )

    assert state["stage"] == "element_kind"
    assert state["relationship_draft"] is None
    assert state["current"] == {
        "capture_scope": "required_participant_replacement",
        "return_stage": "obligation_resolution",
        "superseded_element_id": "element-000031",
    }
    prompt = PROJECTION_INTERVIEW._prompt(
        PROJECTION_INTERVIEW._question(
            state, purpose=REAL_PURPOSE, contract=13,
        ),
        state,
    )
    assert "Required participant replacement capture" in prompt
    assert "record the other visible endpoint" not in prompt


def test_misdirected_required_participant_gap_is_reopened_append_only() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=13)
    state["elements"] = [{
        "id": "element-000031", "kind": "annotation", "region": [694, 385, 800, 428],
        "status": "gap", "content": "", "gap_reason": "Clipped by region crop.",
    }, {
        "id": "element-000032", "kind": "metric", "region": [477, 349, 650, 405],
        "status": "readable", "content": "Capture rate: 18.2%.", "gap_reason": "",
    }]
    state["relationships"] = [{
        "id": "relationship-000035", "kind": "annotation arrow",
        "from_id": None, "to_id": "element-000032", "status": "gap",
        "description": "", "gap_reason": "The origin could not be bound.",
        "binding_method": "coordinate_unique_containment",
        "binding_issue": {
            "participant": "origin", "point": [750, 405],
            "matching_element_ids": [], "reason": "no_unique_recorded_element",
        },
    }]
    state["relationship_obligations"] = [{
        "id": "obligation-000030", "element_id": "element-000031",
        "status": "resolved", "resolution": "gap",
        "relationship_id": "relationship-000035",
    }]
    history = [{
        "event": "answer_recorded", "question_id": "relationship_binding_resolution",
        "accepted": True, "parsed": "record_visible_endpoint", "sequence": 3625,
    }, {
        "event": "element_superseded", "element_id": "element-000032",
        "sequence": 3652,
    }, {
        "event": "answer_recorded", "question_id": "relationship_binding_resolution",
        "accepted": True, "parsed": "record_endpoint_gap", "sequence": 3658,
    }]

    event = PROJECTION_INTERVIEW._misdirected_participant_gap_migration(
        state, history,
    )
    assert event is not None
    PROJECTION_INTERVIEW._apply_misdirected_participant_gap_migration(
        state, event,
    )

    assert state["relationships"][0]["resolution_status"] == "invalidated"
    assert state["relationship_obligations"][0] == {
        "id": "obligation-000030", "element_id": "element-000031",
        "status": "pending", "resolution": None, "relationship_id": None,
    }


def test_relationship_counter_uses_replayed_semantic_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = [{
        "event": "question_asked",
        "question": {"context": {"intake_purpose": REAL_PURPOSE}},
    }, {
        "event": "answer_recorded", "accepted": True,
        "question_id": "relationship_description",
    }]
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview, "_read_journal",
        lambda _journal: entries,
    )
    monkeypatch.setattr(
        CODEX_RUNNER.projection_interview, "_replay",
        lambda _entries, *, purpose, contract: (
            {"relationships": []}, None, False,
        ),
    )

    assert CODEX_RUNNER._projection_relationship_outcome_count(
        tmp_path / "interview.jsonl",
    ) == 0


def test_rejected_endpoint_is_not_a_same_unit_collision_candidate() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["rejected_endpoint_collision_excluded_enabled"] = True
    state["elements"] = [{
        "id": "element-000062", "kind": "metric", "region": [363, 326, 407, 350],
        "status": "gap", "content": "", "gap_reason": "Rejected by exact crop.",
        "capture_scope": "relationship_endpoint",
        "endpoint_verification": {
            "verdict": "does_not_contain_claimed_content",
        },
    }]
    current = {
        "left": 355, "top": 318, "right": 425, "bottom": 365,
        "capture_scope": "relationship_endpoint",
    }

    assert PROJECTION_INTERVIEW._element_collision_candidates(
        state, current,
    ) == []


def test_region_gap_remains_a_same_unit_collision_candidate() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["rejected_endpoint_collision_excluded_enabled"] = True
    state["elements"] = [{
        "id": "element-000028", "kind": "annotation", "region": [376, 465, 550, 568],
        "status": "gap", "content": "", "gap_reason": "Clipped at the edge.",
        "capture_scope": "region-r03-c02",
    }]
    current = {
        "left": 400, "top": 500, "right": 520, "bottom": 560,
        "capture_scope": "relationship_endpoint",
    }

    candidates = PROJECTION_INTERVIEW._element_collision_candidates(state, current)

    assert [item["id"] for item in candidates] == ["element-000028"]


def test_collision_activation_recovers_pending_rejected_merge_question() -> None:
    state = PROJECTION_INTERVIEW._initial_state(contract=12)
    state["elements"] = [{
        "id": "element-000062", "kind": "metric", "region": [363, 326, 407, 350],
        "status": "gap", "content": "", "gap_reason": "Rejected by exact crop.",
        "capture_scope": "relationship_endpoint",
        "endpoint_verification": {
            "verdict": "does_not_contain_claimed_content",
        },
    }]
    state["current"] = {
        "kind": "metric", "left": 355, "top": 318, "right": 425,
        "bottom": 365, "capture_scope": "relationship_endpoint",
        "return_stage": "relationship_target_x",
        "unit_collision_candidate_ids": ["element-000062"],
        "superseded_element_id": "element-000062",
        "merge_left": 355,
    }
    state["stage"] = "element_merge_top"
    pending = {
        "id": "element_merge_top",
    }

    event = PROJECTION_INTERVIEW._rejected_endpoint_collision_activation(
        state, pending, contract=12,
    )
    PROJECTION_INTERVIEW._apply_rejected_endpoint_collision_activation(
        state, event,
    )

    assert state["stage"] == "element_status"
    assert "unit_collision_candidate_ids" not in state["current"]
    assert "superseded_element_id" not in state["current"]
    assert "merge_left" not in state["current"]
    assert state["rejected_endpoint_collision_excluded_enabled"] is True


def test_first_spreadsheet_projection_preserves_structure_formulas_and_gaps(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "dashboard-data.bin"
    supplied.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)

    result = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    assert result["status"] == "ready_for_projection_assessment", result
    projection_bytes = (work / result["projection"]["path"]).read_bytes()
    projected = json.loads(projection_bytes)

    assert result["stopped"] == "first_spreadsheet_projection_recorded"
    assert result["projection"]["method"] == "spreadsheet_ooxml_v1"
    assert [sheet["name"] for sheet in projected["workbook"]["sheets"]] == [
        "Dashboard Inputs",
        "Hidden Logic",
    ]
    assert projected["workbook"]["sheets"][1]["state"] == "hidden"
    assert projected["workbook"]["sheets"][0]["cells"][2]["formula"] == "A2/364"
    assert projected["coverage"]["source_units"] == len(
        projected["coverage"]["parts"]
    )
    assert projected["coverage"]["represented_units"] + projected["coverage"]["gap_units"] == projected["coverage"]["source_units"]
    assert projected["coverage"]["gap_units"] == 1
    assert START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE) == result
    boundary = START_INTAKE.run_clarification_boundary(work)
    assert boundary["boundary"] == "first_source_projection_complete"
    assert START_INTAKE.run_source_projection_closure(work)["verdict"] == "all_projected"


def test_corrupt_spreadsheet_records_one_replayable_failed_outcome(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "corrupt.xlsx"
    supplied.write_bytes(_representative_workbook_bytes(missing_workbook=True))
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)

    result = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    ledger = (work / "ledger.jsonl").read_bytes()

    assert result["stopped"] == "first_spreadsheet_projection_failed"
    assert result["projection"]["status"] == "failed"
    assert "missing xl/workbook.xml" in result["projection"]["coverage"]["gaps"][0]
    assert START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE) == result
    boundary = START_INTAKE.run_clarification_boundary(work)
    assert boundary["boundary"] == "source_conversion_failed"
    assert (work / "ledger.jsonl").read_bytes() == ledger
    closure = START_INTAKE.run_source_projection_closure(work)
    assert closure["verdict"] == "conversion_incomplete"
    assert closure["outcomes"][-1]["outcome"] == "failed"


def test_additional_spreadsheet_uses_the_same_deterministic_projection(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_to_frozen_image(work, tmp_path / "first.png")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    projection_answers = iter(
        _projection_answers(contract=PROJECTION_INTERVIEW.CONTRACT)
    )
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
        "spreadsheet-questioner",
        "pytest-spreadsheet-gap",
        "local_file",
        "Which spreadsheet contains the missing logic?",
    ])
    START_INTAKE.run_gap_clarification(
        work,
        input_fn=lambda _prompt: next(question_answers),
        output_fn=lambda _message: None,
    )
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    frozen = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, gap_file=supplied
    )

    result = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )

    assert frozen["stopped"] == "additional_source_frozen"
    assert result["stopped"] == "additional_source_projection_recorded"
    assert result["projection"]["method"] == "spreadsheet_ooxml_v1"
    assert result["projection"]["id"] == frozen["projection"]["id"]
    assert START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE) == result
    boundary = START_INTAKE.run_clarification_boundary(work)
    assert boundary["boundary"] == "additional_source_projection_complete"
    assert START_INTAKE.run_source_projection_closure(work)["verdict"] == "all_projected"


def test_completed_intake_reopens_source_collection_append_only(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_readable_text_to_terminal(work, tmp_path / "generator.py")
    ledger_before = (work / "ledger.jsonl").read_bytes()
    entries_before = [
        json.loads(line)
        for line in ledger_before.decode("utf-8").splitlines()
        if line.strip()
    ]
    terminal = entries_before[-1]

    reopened = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        begin_source_collection=True,
    )
    ledger_after = (work / "ledger.jsonl").read_bytes()
    entries_after = [
        json.loads(line)
        for line in ledger_after.decode("utf-8").splitlines()
        if line.strip()
    ]

    assert reopened["status"] == "needs_operator"
    assert reopened["stopped"] == "awaiting_source_collection_decision"
    assert reopened["question"]["allowed_values"] == [
        "add_source",
        "finish_sources",
    ]
    assert ledger_after.startswith(ledger_before)
    assert [entry["event"] for entry in entries_after[-2:]] == [
        "source_collection_reopened",
        "operator_question_asked",
    ]
    assert entries_after[-2]["previous_terminal_ledger_sequence"] == terminal[
        "sequence"
    ]
    assert entries_after[-2]["previous_terminal_entry_sha256"] == terminal[
        "entry_sha256"
    ]
    assert entries_after[-1]["reopen_ledger_sequence"] == entries_after[-2][
        "sequence"
    ]
    assert START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE) == reopened
    assert (work / "ledger.jsonl").read_bytes() == ledger_after


def test_completed_intake_reopen_rejects_combined_input_without_mutation(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_readable_text_to_terminal(work, tmp_path / "generator.py")
    ledger_before = (work / "ledger.jsonl").read_bytes()
    extra = tmp_path / "extra.py"
    extra.write_text("VALUE = 1\n", encoding="utf-8")

    refused = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source=extra,
        begin_source_collection=True,
    )

    assert refused["status"] == "blocked"
    assert refused["stopped"] == "source collection reopen invocation invalid"
    assert (work / "ledger.jsonl").read_bytes() == ledger_before


def test_completed_intake_launcher_uses_code_controlled_choice() -> None:
    result = {
        "status": "first_layer_complete",
        "stopped": "effective_first_layer_terminal_recorded",
    }
    answers = iter(["not-an-option", "add_source"])
    messages: list[str] = []

    selected = INTAKE_RUNNER._completed_intake_action(
        result,
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )

    assert selected == "add_source"
    assert any("choose one of: return_result, add_source" in item for item in messages)
    assert INTAKE_RUNNER._completed_intake_action(
        {"status": "needs_operator"},
        input_fn=lambda _prompt: pytest.fail("nonterminal state must not ask"),
        output_fn=messages.append,
    ) is None


def test_completed_intake_launcher_adds_source_and_reaches_new_terminal(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_readable_text_to_terminal(work, tmp_path / "generator.py")
    ledger_before = (work / "ledger.jsonl").read_bytes()
    extra = tmp_path / "second-generator.py"
    extra.write_text("VALUE = 'capture_rate'\n", encoding="utf-8")
    answers = iter([
        "add_source",
        "add_source",
        "local_file",
        str(extra),
        "finish_sources",
    ])
    prompts: list[str] = []

    returncode = INTAKE_RUNNER._continue_intake(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        input_fn=lambda prompt: (prompts.append(prompt), next(answers))[1],
        output_fn=lambda _message: None,
        model_run_fn=lambda *_args, **_kwargs: pytest.fail(
            "verbatim source must not invoke a model"
        ),
        projection_region_limit=None,
        projection_relationship_limit=None,
    )
    state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    ledger_after = (work / "ledger.jsonl").read_bytes()

    assert returncode == 0
    assert len(prompts) == 5
    assert state["status"] == "first_layer_complete"
    assert state["effective_first_layer_terminal"]["disposition"][
        "source_count"
    ] == 4
    assert ledger_after.startswith(ledger_before)
    assert sum(
        json.loads(line)["event"] == "source_collection_reopened"
        for line in ledger_after.decode("utf-8").splitlines()
        if line.strip()
    ) == 1

    replay_code = INTAKE_RUNNER._continue_intake(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        input_fn=lambda _prompt: "return_result",
        output_fn=lambda _message: None,
        model_run_fn=lambda *_args, **_kwargs: pytest.fail("model must not run"),
        projection_region_limit=None,
        projection_relationship_limit=None,
    )
    assert replay_code == 0
    assert (work / "ledger.jsonl").read_bytes() == ledger_after


def test_post_projection_source_decision_is_an_explicit_external_boundary(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_readable_text_to_terminal(work, tmp_path / "generator.py")
    extra = tmp_path / "second-generator.py"
    extra.write_text("VALUE = 'capture_rate'\n", encoding="utf-8")
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        begin_source_collection=True,
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="add_source",
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_kind="local_file",
    )
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, extra)
    projected = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        project_source=True,
    )

    boundary = START_INTAKE.run_clarification_boundary(work)

    assert projected["stopped"] == "additional_source_projection_recorded"
    assert boundary["boundary"] == "source_collection_answer_required"
    assert boundary["status"] == "needs_operator"
    assert boundary["stopped"] == "awaiting_source_collection_decision"
    assert boundary["question"]["allowed_values"] == [
        "add_source",
        "finish_sources",
    ]
    assert CODEX_RUNNER.BOUNDARY_EXIT_CODES[
        "source_collection_answer_required"
    ] == 4


def test_launcher_resumes_only_an_operator_projection_boundary(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    _advance_readable_text_to_terminal(work, tmp_path / "generator.py")
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        begin_source_collection=True,
    )
    ledger_before = (work / "ledger.jsonl").read_bytes()

    preserved = INTAKE_RUNNER._resume_after_projection_boundary(
        3,
        work,
        "There is a new intake",
        REAL_PURPOSE,
        input_fn=lambda _prompt: pytest.fail("a non-operator code must not prompt"),
        output_fn=lambda _message: pytest.fail("a non-operator code must not output"),
        model_run_fn=lambda *_args, **_kwargs: pytest.fail("model must not run"),
        projection_region_limit=None,
        projection_relationship_limit=None,
    )
    answers = iter(["finish_sources"])
    prompts: list[str] = []
    resumed = INTAKE_RUNNER._resume_after_projection_boundary(
        4,
        work,
        "There is a new intake",
        REAL_PURPOSE,
        input_fn=lambda prompt: (prompts.append(prompt), next(answers))[1],
        output_fn=lambda _message: None,
        model_run_fn=lambda *_args, **_kwargs: pytest.fail("model must not run"),
        projection_region_limit=None,
        projection_relationship_limit=None,
    )

    assert preserved == 3
    assert (work / "ledger.jsonl").read_bytes().startswith(ledger_before)
    assert resumed == 0
    assert len(prompts) == 1
    state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "first_layer_complete"


def test_operator_launcher_prepares_first_qualification_clarification_question(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    answer = tmp_path / "supporting-reference.xlsx"
    answer.write_bytes(_representative_workbook_bytes())
    followup_answer = tmp_path / "supporting-logic.py"
    followup_answer.write_text("FORMULA = 'net_revenue / transactions'\n")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    messages: list[str] = []
    answers = iter([
        "finish_sources",
        "provide_answer",
        str(answer),
        "provide_answer",
        str(followup_answer),
    ])

    def run_model(_argv: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        assert check is False
        active_state = json.loads(
            (work / "intake-state.json").read_text(encoding="utf-8")
        )
        if active_state["phase"] == "formulating_qualification_question_round":
            model_answers = iter([
                "local_file",
                "Please provide the workbook source containing this missing part?",
            ])
            prepared = START_INTAKE.run_qualification_question_round(
                work,
                input_fn=lambda _prompt: next(model_answers),
                output_fn=lambda _message: None,
            )
            assert prepared["status"] == "needs_operator"
        elif (
            active_state["phase"]
            == "formulating_qualification_followup_question_round"
        ):
            model_answers = iter([
                "local_file",
                "Please provide a different source that contains this missing part?",
            ])
            prepared = START_INTAKE.run_qualification_followup_question_round(
                work,
                input_fn=lambda _prompt: next(model_answers),
                output_fn=lambda _message: None,
            )
            assert prepared["status"] == "needs_operator"
        else:
            assert active_state["phase"] == "assessing_qualification_answers"
            assessment_answers = iter([
                "codex",
                "qualification-answer-assessment",
                "resolves_obligation",
                "The supplied workbook contains the exact requested unit.",
            ])
            assessed = START_INTAKE.run_qualification_answer_assessment(
                work,
                input_fn=lambda _prompt: next(assessment_answers),
                output_fn=lambda _message: None,
            )
            assert assessed["status"] == (
                "qualification_answer_assessment_complete"
            )
        return subprocess.CompletedProcess(_argv, 0)

    returncode = INTAKE_RUNNER._continue_intake(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
        model_run_fn=run_model,
        projection_region_limit=None,
        projection_relationship_limit=None,
    )

    state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    assert returncode == 0
    assert state["phase"] == "effective_first_layer_terminal_recorded"
    assert state["effective_first_layer_terminal"]["disposition"][
        "disposition"
    ] == "first_layer_complete"
    assert len(state["qualification_followup_questions"]) == 1
    assert len(state["qualification_followup_answers"]) == 1
    assert len(state["qualification_question_answers"]) == 1


def test_operator_launcher_interviews_one_source_collection_answer_at_a_time(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    workbook = tmp_path / "reference.xlsx"
    workbook.write_bytes(_representative_workbook_bytes())
    generator = tmp_path / "generator.py"
    generator.write_text("FORMULA = 'A2/364'\n", encoding="utf-8")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, workbook)
    answers = iter([
        "add_source",
        "local_file",
        str(generator),
        "finish_sources",
        "provide_answer",
        str(generator),
    ])
    prompts: list[str] = []

    def run_model(_argv: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        assert check is False
        active_state = json.loads(
            (work / "intake-state.json").read_text(encoding="utf-8")
        )
        if active_state["phase"] == "formulating_qualification_question_round":
            model_answers = iter([
                "local_file",
                "Please provide the workbook source containing this missing part?",
            ])
            prepared = START_INTAKE.run_qualification_question_round(
                work,
                input_fn=lambda _prompt: next(model_answers),
                output_fn=lambda _message: None,
            )
            assert prepared["status"] == "needs_operator"
        else:
            assert active_state["phase"] == "assessing_qualification_answers"
            assessment_answers = iter([
                "codex",
                "qualification-answer-assessment",
                "resolves_obligation",
                "The supplied source contains the requested unit.",
            ])
            assessed = START_INTAKE.run_qualification_answer_assessment(
                work,
                input_fn=lambda _prompt: next(assessment_answers),
                output_fn=lambda _message: None,
            )
            assert assessed["status"] == (
                "qualification_answer_assessment_complete"
            )
        return subprocess.CompletedProcess(_argv, 0)

    returncode = INTAKE_RUNNER._continue_intake(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        input_fn=lambda prompt: (prompts.append(prompt), next(answers))[1],
        output_fn=lambda _message: None,
        model_run_fn=run_model,
        projection_region_limit=None,
        projection_relationship_limit=None,
    )

    assert returncode == 0
    assert len(prompts) == 6
    assert START_INTAKE.run_source_projection_closure(work)["source_count"] == 5
    state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    assert state["phase"] == "effective_first_layer_terminal_recorded"


def test_independent_source_collection_adds_projects_and_closes_replayably(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    workbook = tmp_path / "reference.xlsx"
    workbook.write_bytes(_representative_workbook_bytes())
    generator = tmp_path / "generate_reference.py"
    generator.write_text(
        "def net_revenue(values):\n    return sum(values)\n",
        encoding="utf-8",
    )
    supporting_workbook = tmp_path / "supporting-reference.xlsx"
    supporting_workbook.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, workbook)
    first = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    assert first["stopped"] == "first_spreadsheet_projection_recorded"

    decision = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        begin_source_collection=True,
    )
    assert decision["status"] == "needs_operator"
    assert decision["question"]["allowed_values"] == [
        "add_source",
        "finish_sources",
    ]
    kind = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="add_source",
    )
    assert kind["question"]["allowed_values"] == ["local_file", "url"]
    requested = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_kind="local_file",
    )
    assert requested["question"]["answer_type"] == "local_file"

    frozen = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, generator
    )
    assert frozen["stopped"] == "additional_source_frozen"
    assert frozen["source"]["id"] == "source-000004"
    assert frozen["projection"]["id"] == "projection-source-000004-v1"
    projected = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    assert projected["stopped"] == "additional_source_projection_recorded"
    assert projected["projection"]["method"] == "verbatim_utf8"

    next_decision = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE
    )
    assert next_decision["question"]["allowed_values"] == [
        "add_source",
        "finish_sources",
    ]
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="add_source",
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_kind="local_file",
    )
    second_frozen = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, supporting_workbook
    )
    assert second_frozen["source"]["id"] == "source-000005"
    second_projected = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    assert second_projected["projection"]["method"] == "spreadsheet_ooxml_v1"
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    completed = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    ledger_before_replay = (work / "ledger.jsonl").read_bytes()

    assert completed["status"] == "source_collection_complete"
    assert completed["source_collection"]["source_ids"] == [
        "source-000001",
        "source-000002",
        "source-000003",
        "source-000004",
        "source-000005",
    ]
    assert completed["source_projection_closure"]["verdict"] == "all_projected"
    assert START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE
    ) == completed
    assert (work / "ledger.jsonl").read_bytes() == ledger_before_replay
    events = [
        json.loads(line)["event"]
        for line in ledger_before_replay.decode("utf-8").splitlines()
    ]
    assert events.count("source_collection_completed") == 1
    assert "model_additional_source_gap_assessment_requested" not in events


def test_source_collection_refuses_finish_while_projection_is_pending(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    workbook = tmp_path / "reference.xlsx"
    workbook.write_bytes(_representative_workbook_bytes())
    generator = tmp_path / "generate_reference.py"
    generator.write_text("VALUE = 1\n", encoding="utf-8")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, workbook)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="add_source",
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_kind="local_file",
    )
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, generator)

    result = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )

    assert result["status"] == "blocked"
    assert result["stopped"] == "source projection pending"
    assert "source_collection_completed" not in (
        work / "ledger.jsonl"
    ).read_text(encoding="utf-8")


def test_independent_image_source_enters_existing_visual_projection_path(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    workbook = tmp_path / "reference.xlsx"
    workbook.write_bytes(_representative_workbook_bytes())
    image = tmp_path / "clean-reference.png"
    Image.new("RGB", (64, 48), "white").save(image)
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, workbook)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="add_source",
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_kind="local_file",
    )
    frozen = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, image
    )

    result = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )

    assert frozen["source"]["id"] == "source-000004"
    assert result["status"] == "waiting_for_model"
    assert result["stopped"] == "interviewing_additional_source_projection"
    assert result["lineage"]["mode"] == "independent_source_collection"
    assert result["work"][0]["stage"] == "project_additional_source"


def test_source_collection_probe_units_reject_ambiguous_identity_and_coverage() -> None:
    with pytest.raises(ValueError, match="duplicate source identity"):
        START_INTAKE.source_collection_reservation.reserve(
            ["source-000003", "source-000003"]
        )
    result = START_INTAKE.source_collection_closure.reconcile(
        ["source-000003", "source-000005"],
        [
            {"source_id": "source-000003", "outcome": "projected"},
            {"source_id": "source-999999", "outcome": "failed"},
        ],
    )
    assert result["complete"] is False
    assert "missing outcomes: source-000005" in result["why"]
    assert "unknown outcomes: source-999999" in result["why"]


def test_source_set_qualification_admits_every_collected_source_replayably(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    workbook = tmp_path / "reference.xlsx"
    workbook.write_bytes(_representative_workbook_bytes())
    generator = tmp_path / "generate_reference.py"
    generator.write_text("FORMULA = 'A2/364'\n", encoding="utf-8")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, workbook)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="add_source",
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_kind="local_file",
    )
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, generator)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )

    START_INTAKE.run_source_set_qualification(work)
    qualified = START_INTAKE.run_qualification_admission(work)
    ledger_after = (work / "ledger.jsonl").read_bytes()
    replay = START_INTAKE.run_qualification_admission(work)

    assert qualified["status"] == "qualification_admission_complete"
    assert qualified["route"] == "clarification_required"
    assert qualified["source_set_qualification"]["qualification"] == (
        "readable_source_set_incomplete"
    )
    outcomes = qualified["source_set_qualification"]["outcomes"]
    assert [item["source_id"] for item in outcomes] == [
        "source-000001",
        "source-000002",
        "source-000003",
        "source-000004",
    ]
    assert [item["qualification"] for item in outcomes] == [
        "readable_projection_complete",
        "readable_projection_complete",
        "readable_projection_incomplete",
        "readable_projection_complete",
    ]
    assert outcomes[2]["gaps"] == [
        {
            "source_id": "source-000003",
            "unit": "xl/customData/metrics.xml",
            "reason": (
                "workbook part xl/customData/metrics.xml has no readable adapter"
            ),
        }
    ]
    obligation = qualified["clarification_obligations"][0]
    qualification_event = [
        json.loads(line)
        for line in ledger_after.decode("utf-8").splitlines()
        if json.loads(line)["event"] == "source_set_qualification_completed"
    ][0]
    assert obligation["source_id"] == "source-000003"
    assert obligation["projection_id"] == outcomes[2]["projection_id"]
    assert obligation["projection_sha256"] == outcomes[2]["projection_sha256"]
    assert obligation["method"] == "spreadsheet_ooxml_v1"
    assert obligation["qualification_event_sha256"] == qualification_event[
        "entry_sha256"
    ]
    assert len(obligation["gap_sha256"]) == 64
    assert replay == qualified
    assert (work / "ledger.jsonl").read_bytes() == ledger_after
    events = [
        json.loads(line)["event"]
        for line in ledger_after.decode("utf-8").splitlines()
    ]
    assert events.count("source_set_qualification_completed") == 1
    assert events.count("qualification_admission_completed") == 1


def test_qualification_admission_closes_an_all_readable_source_set(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    generator = tmp_path / "generate_reference.py"
    generator.write_text("VALUE = 1\n", encoding="utf-8")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, generator)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)

    admitted = START_INTAKE.run_qualification_admission(work)
    ledger_after = (work / "ledger.jsonl").read_bytes()

    assert admitted["status"] == "qualification_admission_complete"
    assert admitted["route"] == "first_layer_complete"
    assert admitted["clarification_obligations"] == []
    assert START_INTAKE.run_qualification_admission(work) == admitted
    assert (work / "ledger.jsonl").read_bytes() == ledger_after

    terminal = START_INTAKE.run_clarification_boundary(work)

    assert terminal["boundary"] == "first_layer_complete"
    assert terminal["status"] == "first_layer_complete"
    assert terminal["remaining_gap_count"] == 0
    assert terminal["remaining_gaps"] == []


def test_qualification_admission_preserves_a_conversion_failure_obligation(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "corrupt.xlsx"
    supplied.write_bytes(_representative_workbook_bytes(missing_workbook=True))
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    failed = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)

    admitted = START_INTAKE.run_qualification_admission(work)

    assert failed["stopped"] == "first_spreadsheet_projection_failed"
    assert admitted["route"] == "clarification_required"
    obligation = admitted["clarification_obligations"][0]
    assert obligation["source_id"] == "source-000003"
    assert obligation["projection_id"] is None
    assert obligation["projection_sha256"] is None
    assert obligation["method"] is None
    assert obligation["qualification"] == "conversion_incomplete"
    assert obligation["unit"] == "projection"
    assert "missing xl/workbook.xml" in obligation["reason"]


def test_qualification_clarification_round_reaches_one_operator_question(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    admitted = START_INTAKE.run_qualification_admission(work)

    requested = START_INTAKE.request_qualification_question_round(work)
    attachments, command = CODEX_RUNNER.load_request(work)
    answers = iter([
        "local_file",
        "Please provide the workbook source containing this missing part?",
    ])
    prepared = START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )
    ledger_after = (work / "ledger.jsonl").read_bytes()

    assert admitted["route"] == "clarification_required"
    assert requested["status"] == "waiting_for_model"
    assert requested["stopped"] == "formulating_qualification_question_round"
    assert attachments == ()
    assert command[-1] == "--run-qualification-question-round"
    assert prepared["status"] == "needs_operator"
    assert prepared["stopped"] == "awaiting_qualification_clarification_answers"
    assert prepared["question"] == prepared["questions"][0]
    assert len(prepared["questions"]) == len(admitted["clarification_obligations"])
    assert prepared["question"]["answers_obligation"] == admitted[
        "clarification_obligations"
    ][0]
    assert START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE) == prepared
    assert (work / "ledger.jsonl").read_bytes() == ledger_after
    events = [
        json.loads(line)["event"]
        for line in ledger_after.decode("utf-8").splitlines()
    ]
    assert events[-4:] == [
        "qualification_question_round_requested",
        "qualification_question_round_completed",
        "operator_qualification_question_round_prepared",
        "operator_qualification_question_asked",
    ]


def test_qualification_local_file_answer_enters_through_real_operator_turn(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    START_INTAKE.run_qualification_admission(work)
    START_INTAKE.request_qualification_question_round(work)
    model_answers = iter([
        "local_file",
        "Please provide the workbook source containing this missing part?",
    ])
    START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(model_answers),
        output_fn=lambda _message: None,
    )
    answer = tmp_path / "supporting-reference.xlsx"
    answer.write_bytes(_representative_workbook_bytes())
    iter_answers = iter(["provide_answer", str(answer)])

    result = START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda _prompt: next(iter_answers),
        output_fn=lambda _message: None,
    )

    assert result["status"] == "ready_for_projection", result
    assert result["stopped"] == "additional_source_frozen"
    assert result["source"]["answers_question"] == (
        "qualification-clarification-answer-000001"
    )
    assert result["source"]["answers_obligation"]["unit"] == (
        "xl/customData/metrics.xml"
    )
    assert result["lineage"]["mode"] == "qualification_clarification_answer"
    completed = START_INTAKE.run_clarification_boundary(work)
    replay_ledger = (work / "ledger.jsonl").read_bytes()

    assert completed["boundary"] == "needs_model_interview"
    assert completed["stopped"] == "assessing_qualification_answers"
    saved = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    answer_record = saved["qualification_question_answers"][0]
    assert answer_record["source"]["sha256"] == result["source"]["sha256"]
    assert answer_record["projection"]["source_id"] == result["source"]["id"]
    assert START_INTAKE.run_clarification_boundary(work) == completed
    assert (work / "ledger.jsonl").read_bytes() == replay_ledger


def test_qualification_operator_can_preserve_an_unavailable_gap(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    START_INTAKE.run_qualification_admission(work)
    START_INTAKE.request_qualification_question_round(work)
    model_answers = iter([
        "local_file",
        "Please provide the workbook source containing this missing part?",
    ])
    START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(model_answers),
        output_fn=lambda _message: None,
    )
    outputs: list[str] = []

    preserved = START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda _prompt: "preserve_gap",
        output_fn=outputs.append,
    )

    assert outputs[-1] == (
        "Allowed actions: provide_answer, preserve_gap"
    )
    assert preserved["status"] == "ready_for_qualification_assessment"
    assert preserved["stopped"] == "qualification_question_round_answered"
    state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    answer = state["qualification_question_answers"][0]
    assert answer["submission"] == {
        "channel": "preserve_gap",
        "value": "preserve_gap",
    }
    assert (work / answer["source"]["path"]).read_text(encoding="utf-8") == (
        "preserve_gap"
    )
    assessment_answers = iter([
        "codex",
        "qualification-answer-assessment",
        "does_not_resolve_obligation",
        "The operator explicitly preserved the unavailable information as a gap.",
    ])
    START_INTAKE.request_qualification_answer_assessment(work)
    START_INTAKE.run_qualification_answer_assessment(
        work,
        input_fn=lambda _prompt: next(assessment_answers),
        output_fn=lambda _message: None,
    )
    admitted = START_INTAKE.run_qualification_resolution_admission(work)
    closed = START_INTAKE.run_qualification_obligation_closure(work)
    terminal = START_INTAKE.run_effective_first_layer_terminal(work)
    ledger_after = (work / "ledger.jsonl").read_bytes()

    assert admitted["preserved_gap_count"] == 1
    assert closed["preserved_gap_obligation_ids"] == [
        "clarification-obligation-000001"
    ]
    assert closed["unresolved_obligation_ids"] == []
    assert terminal["status"] == "first_layer_complete_with_preserved_gaps"
    assert terminal["preserved_gap_count"] == 1
    assert terminal["remaining_gap_count"] == 0
    boundary_result = START_INTAKE._clarification_boundary_result(
        terminal, "first_layer_complete_with_preserved_gaps"
    )
    assert boundary_result == {
        **terminal,
        "boundary": "first_layer_complete_with_preserved_gaps",
    }
    cli_boundary = subprocess.run(
        [sys.executable, str(SCRIPT), "--work", str(work), "--clarification-boundary"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert cli_boundary.returncode == 0
    assert json.loads(cli_boundary.stdout)["status"] == (
        "first_layer_complete_with_preserved_gaps"
    )
    assert START_INTAKE.run_effective_first_layer_terminal(work) == terminal
    assert (work / "ledger.jsonl").read_bytes() == ledger_after

    reopened = START_INTAKE._reopen_completed_source_collection(
        work,
        json.loads((work / "intake-state.json").read_text(encoding="utf-8")),
        [
            json.loads(line)
            for line in (work / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ],
    )
    assert reopened["status"] == "needs_operator"
    assert reopened["stopped"] == "awaiting_source_collection_decision"
    assert reopened["question"]["allowed_values"] == [
        "add_source",
        "finish_sources",
    ]


def test_reopened_source_collection_uses_a_new_qualification_question_round(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    admitted = START_INTAKE.run_qualification_admission(work)
    START_INTAKE.request_qualification_question_round(work)
    question_answers = iter(
        [
            answer
            for _obligation in admitted["clarification_obligations"]
            for answer in ("local_file", "Provide the missing source?")
        ]
    )
    START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(question_answers),
        output_fn=lambda _message: None,
    )
    START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda _prompt: "preserve_gap",
        output_fn=lambda _message: None,
    )
    assessment_answers = iter([
        "codex",
        "qualification-answer-assessment",
        "does_not_resolve_obligation",
        "The unavailable source remains an explicit gap.",
    ])
    START_INTAKE.request_qualification_answer_assessment(work)
    START_INTAKE.run_qualification_answer_assessment(
        work,
        input_fn=lambda _prompt: next(assessment_answers),
        output_fn=lambda _message: None,
    )
    START_INTAKE.run_qualification_resolution_admission(work)
    START_INTAKE.run_qualification_obligation_closure(work)
    START_INTAKE.run_effective_first_layer_terminal(work)
    first_round = work / "qualification-question-round"
    first_round_journal = (first_round / "interview.jsonl").read_bytes()
    first_round_result = (first_round / "question-round.json").read_bytes()

    extra = tmp_path / "supporting.py"
    extra.write_text("VALUE = 'supporting evidence'\n", encoding="utf-8")
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="add_source",
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_kind="local_file",
    )
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, extra)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE)
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    readmitted = START_INTAKE.run_qualification_admission(work)

    requested = START_INTAKE.request_qualification_question_round(work)
    state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))

    assert requested["status"] == "waiting_for_model"
    assert state["qualification_question_round"]["directory"] != (
        "qualification-question-round"
    )
    assert (
        work / state["qualification_question_round"]["directory"] / "interview.jsonl"
    ).is_file()
    assert (first_round / "interview.jsonl").read_bytes() == first_round_journal
    assert (first_round / "question-round.json").read_bytes() == first_round_result

    second_answers = iter(
        [
            answer
            for _obligation in readmitted["clarification_obligations"]
            for answer in ("local_file", "Provide the newly missing source?")
        ]
    )
    START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(second_answers),
        output_fn=lambda _message: None,
    )
    for _obligation in readmitted["clarification_obligations"]:
        START_INTAKE.run_operator_turn(
            work,
            input_fn=lambda _prompt: "preserve_gap",
            output_fn=lambda _message: None,
        )
    assessment_request = START_INTAKE.request_qualification_answer_assessment(work)

    assert assessment_request["status"] == "waiting_for_model"
    assert assessment_request["stopped"] == "assessing_qualification_answers"
    attachments, command = CODEX_RUNNER.load_request(work)
    assert attachments == ()
    assert command[-1] == "--run-qualification-answer-assessment"


def test_qualification_answers_advance_once_in_prepared_order(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    workbook = io.BytesIO(_representative_workbook_bytes())
    with ZipFile(workbook, "a", ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/customData/second.xml", "<metrics><name>second</name></metrics>"
        )
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(workbook.getvalue())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    START_INTAKE.run_qualification_admission(work)
    START_INTAKE.request_qualification_question_round(work)
    model_answers = iter([
        "local_file",
        "Please provide the first missing source?",
        "operator_text",
        "What exact information covers the second missing source?",
    ])
    START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(model_answers),
        output_fn=lambda _message: None,
    )
    answer_file = tmp_path / "supporting.txt"
    answer_file.write_text("first immutable answer\n", encoding="utf-8")
    first_answers = iter(["provide_answer", str(answer_file)])
    START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda _prompt: next(first_answers),
        output_fn=lambda _message: None,
    )

    second = START_INTAKE.run_clarification_boundary(work)
    after_first = json.loads(
        (work / "intake-state.json").read_text(encoding="utf-8")
    )

    assert second["boundary"] == "needs_operator_answer"
    assert second["answered_question_count"] == 1
    assert second["question"] == after_first["questions"][1]
    assert len(after_first["qualification_question_answers"]) == 1
    second_answers = iter(["provide_answer", "second exact operator answer"])
    completed = START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda _prompt: next(second_answers),
        output_fn=lambda _message: None,
    )
    assert completed["stopped"] == "qualification_question_round_answered"
    assert completed["answered_question_count"] == 2
    saved = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    assert [
        item["question_id"] for item in saved["qualification_question_answers"]
    ] == [question["id"] for question in saved["questions"]]


def test_qualification_wrong_answer_channel_refuses_without_mutation(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    START_INTAKE.run_qualification_admission(work)
    START_INTAKE.request_qualification_question_round(work)
    model_answers = iter([
        "local_file",
        "Please provide the workbook source containing this missing part?",
    ])
    START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(model_answers),
        output_fn=lambda _message: None,
    )
    before_ledger = (work / "ledger.jsonl").read_bytes()
    before_state = (work / "intake-state.json").read_bytes()

    refused = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_answer="this is text, not the requested file",
    )

    assert refused["status"] == "blocked"
    assert refused["stopped"] == "qualification answer admission refused"
    assert "provide exactly 'local_file'" in refused["why"]
    assert (work / "ledger.jsonl").read_bytes() == before_ledger
    assert (work / "intake-state.json").read_bytes() == before_state


def test_qualification_changed_frozen_answer_source_refuses_before_projection(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    START_INTAKE.run_qualification_admission(work)
    START_INTAKE.request_qualification_question_round(work)
    model_answers = iter([
        "local_file",
        "Please provide the workbook source containing this missing part?",
    ])
    START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(model_answers),
        output_fn=lambda _message: None,
    )
    answer = tmp_path / "supporting-reference.xlsx"
    answer.write_bytes(_representative_workbook_bytes())
    frozen_answers = iter(["provide_answer", str(answer)])
    frozen = START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda _prompt: next(frozen_answers),
        output_fn=lambda _message: None,
    )
    frozen_path = work / frozen["source"]["stored_path"]
    frozen_path.write_bytes(b"changed after preservation")
    before_ledger = (work / "ledger.jsonl").read_bytes()

    refused = START_INTAKE.run_clarification_boundary(work)

    assert refused["status"] == "blocked"
    assert refused["stopped"] == "invalid ledger"
    assert "frozen additional source" in refused["why"]
    assert (work / "ledger.jsonl").read_bytes() == before_ledger


def test_qualification_url_answer_is_frozen_and_projected_once(
    tmp_path: Path, monkeypatch: object,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    START_INTAKE.run_qualification_admission(work)
    START_INTAKE.request_qualification_question_round(work)
    model_answers = iter([
        "url",
        "Please provide the public source containing this missing part?",
    ])
    START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(model_answers),
        output_fn=lambda _message: None,
    )
    content = b"exact public qualification answer\n"
    connection = _URLConnection(
        _URLResponse(200, [("Content-Type", "text/plain; charset=utf-8")], content)
    )
    monkeypatch.setattr(
        START_INTAKE.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                START_INTAKE.socket.AF_INET,
                START_INTAKE.socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", 443),
            )
        ],
    )
    monkeypatch.setattr(
        START_INTAKE, "_url_connection", lambda *_args: connection
    )

    url_answers = iter(["provide_answer", "https://example.test/answer.txt"])
    frozen = START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda _prompt: next(url_answers),
        output_fn=lambda _message: None,
    )
    completed = START_INTAKE.run_clarification_boundary(work)

    assert frozen["source"]["answers_obligation"]["unit"] == (
        "xl/customData/metrics.xml"
    )
    assert (work / frozen["source"]["stored_path"]).read_bytes() == content
    assert completed["boundary"] == "needs_model_interview"
    assert completed["stopped"] == "assessing_qualification_answers"
    state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    assert state["qualification_question_answers"][0]["submission"] == {
        "channel": "url",
        "value": "https://example.test/answer.txt",
    }


def test_qualification_image_answer_reuses_the_general_projection_interview(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    START_INTAKE.run_qualification_admission(work)
    START_INTAKE.request_qualification_question_round(work)
    model_answers = iter([
        "local_file",
        "Please provide the visual source containing this missing part?",
    ])
    START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(model_answers),
        output_fn=lambda _message: None,
    )
    image_answer = tmp_path / "supporting.png"
    Image.new("RGB", (40, 40), "white").save(image_answer, format="PNG")
    image_answers = iter(["provide_answer", str(image_answer)])
    START_INTAKE.run_operator_turn(
        work,
        input_fn=lambda _prompt: next(image_answers),
        output_fn=lambda _message: None,
    )

    waiting = START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    attachments, command = CODEX_RUNNER.load_request(work)

    assert waiting["status"] == "waiting_for_model"
    assert waiting["stopped"] == "interviewing_additional_source_projection"
    assert waiting["lineage"]["mode"] == "qualification_clarification_answer"
    assert isinstance(attachments, tuple)
    assert command[-1] == "--run-projection-interview"
    ledger = [
        json.loads(line)
        for line in (work / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert ledger[-1]["answers_obligation"]["unit"] == (
        "xl/customData/metrics.xml"
    )
    assert "answers_gap" not in ledger[-1]


def test_qualification_question_round_captures_every_known_question_once(
    tmp_path: Path,
) -> None:
    event_sha256 = "a" * 64
    obligations = [
        {
            "id": f"clarification-obligation-{position:06d}",
            "qualification_event_sha256": event_sha256,
            "source_position": position,
            "gap_position": 1,
            "source_id": f"source-{position + 2:06d}",
            "projection_id": f"projection-source-{position + 2:06d}-v1",
            "projection_sha256": str(position) * 64,
            "method": "spreadsheet_ooxml_v1",
            "qualification": "readable_projection_incomplete",
            "unit": f"xl/missing-{position}.xml",
            "reason": f"workbook part {position} has no readable adapter",
            "gap_sha256": chr(98 + position) * 64,
        }
        for position in (1, 2)
    ]
    admission = {
        "sequence": 10,
        "event": "qualification_admission_completed",
        "previous_entry_sha256": "f" * 64,
        "entry_sha256": "e" * 64,
        "qualification_event_sha256": event_sha256,
        "route": "clarification_required",
        "clarification_obligations": obligations,
    }
    answers = iter([
        "binary",
        "local_file",
        "Please provide the first missing workbook part?",
        "operator_text",
        "What exact value belongs in the second missing workbook part?",
    ])
    messages: list[str] = []
    round_dir = tmp_path / "round"

    result = START_INTAKE.qualification_question_round.run(
        round_dir,
        admission=admission,
        purpose=REAL_PURPOSE,
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )
    journal_after = (round_dir / "interview.jsonl").read_bytes()
    replay, _journal_sha256, _result_sha256 = (
        START_INTAKE.qualification_question_round.validate(
            round_dir,
            admission=admission,
            purpose=REAL_PURPOSE,
        )
    )

    assert replay == result
    assert (round_dir / "interview.jsonl").read_bytes() == journal_after
    assert [question["answer_type"] for question in result["questions"]] == [
        "local_file",
        "operator_text",
    ]
    assert [question["answers_obligation"] for question in result["questions"]] == (
        obligations
    )
    assert len(messages) == 1
    assert "received 'binary'" in messages[0]
    assert "choose exactly one of" in messages[0]


def test_qualification_admission_probe_units_refuse_unbound_evidence() -> None:
    contradictory = START_INTAKE.qualification_terminal_disposition.decide({
        "qualification": "readable_source_set_complete",
        "source_count": 1,
        "outcomes": [{
            "source_id": "source-000003",
            "qualification": "readable_projection_incomplete",
            "gaps": [{
                "source_id": "source-000003",
                "unit": "xl/customData/metrics.xml",
                "reason": "no readable adapter",
            }],
        }],
    })
    misbound = START_INTAKE.clarification_obligation_binding.bind(
        {
            "qualification": "readable_source_set_incomplete",
            "source_count": 1,
            "outcomes": [{
                "source_id": "source-000003",
                "projection_id": "projection-source-000003-v1",
                "projection_sha256": "a" * 64,
                "method": "spreadsheet_ooxml_v1",
                "qualification": "readable_projection_incomplete",
                "gaps": [{
                    "source_id": "source-999999",
                    "unit": "xl/customData/metrics.xml",
                    "reason": "no readable adapter",
                }],
            }],
        },
        "b" * 64,
    )
    complete_with_gap = START_INTAKE.qualification_terminal_disposition.decide({
        "qualification": "readable_source_set_complete",
        "source_count": 1,
        "outcomes": [{
            "source_id": "source-000003",
            "qualification": "readable_projection_complete",
            "gaps": [{
                "source_id": "source-000003",
                "unit": "unexpected",
                "reason": "contradictory gap",
            }],
        }],
    })

    assert contradictory["complete"] is False
    assert "contradicts exact source outcomes" in contradictory["why"]
    assert misbound["complete"] is False
    assert "contradicts its source" in misbound["why"]
    assert complete_with_gap["complete"] is False
    assert "still contains gaps" in complete_with_gap["why"]


def test_source_set_qualification_can_finish_with_all_sources_readable(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    generator = tmp_path / "generate_reference.py"
    generator.write_text("VALUE = 1\n", encoding="utf-8")
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, generator)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )

    qualified = START_INTAKE.run_source_set_qualification(work)

    assert qualified["status"] == "source_set_qualification_complete"
    assert qualified["source_set_qualification"]["qualification"] == (
        "readable_source_set_complete"
    )
    assert all(
        item["qualification"] == "readable_projection_complete"
        for item in qualified["source_set_qualification"]["outcomes"]
    )


def test_source_set_probe_units_reject_mismatch_and_duplicate_outcomes() -> None:
    closure = {
        "outcomes": [
            {
                "source_id": "source-000001",
                "source_sha256": "a" * 64,
                "outcome": "projected",
                "projection": {
                    "ledger_sequence": 1,
                    "id": "projection-000001",
                    "version": 1,
                    "path": "projections/projection-000001.txt",
                    "sha256": "a" * 64,
                },
            }
        ]
    }
    bound = START_INTAKE.source_qualification_binding.bind(
        closure,
        [
            {
                "event": "source_projected",
                "source": {
                    "id": "source-000001",
                    "sha256": "a" * 64,
                },
                "projection": {
                    "id": "projection-000001",
                    "version": 1,
                    "path": "projections/projection-000001.txt",
                    "sha256": "b" * 64,
                    "coverage": {
                        "status": "complete",
                        "source_units": 1,
                        "represented_units": 1,
                        "gaps": [],
                    },
                },
            }
        ],
    )
    duplicate = START_INTAKE.source_qualification_reconciliation.reconcile(
        closure,
        [
            {
                "source_id": "source-000001",
                "qualification": "readable_projection_complete",
            },
            {
                "source_id": "source-000001",
                "qualification": "readable_projection_complete",
            },
        ],
    )

    assert bound["complete"] is False
    assert "projection sha256 differs" in bound["why"]
    assert duplicate["complete"] is False
    assert "duplicate=['source-000001']" in duplicate["why"]


def test_source_set_binding_uses_acquisition_digest_for_later_projection_version() -> None:
    source_sha256 = "a" * 64
    projection_sha256 = "b" * 64
    closure = {
        "outcomes": [{
            "source_id": "source-000003",
            "source_sha256": source_sha256,
            "outcome": "projected",
            "projection": {
                "ledger_sequence": 2,
                "id": "projection-source-000003-v2",
                "version": 2,
                "path": "projections/source-000003-v2.json",
                "sha256": projection_sha256,
            },
        }]
    }
    entries = [
        {
            "event": "source_acquired",
            "source": {
                "id": "source-000003",
                "sha256": source_sha256,
            },
        },
        {
            "event": "projection_version_created",
            "projection": {
                "id": "projection-source-000003-v2",
                "source_id": "source-000003",
                "version": 2,
                "path": "projections/source-000003-v2.json",
                "sha256": projection_sha256,
                "coverage": "unassessed",
            },
        },
    ]

    bound = START_INTAKE.source_qualification_binding.bind(closure, entries)

    assert bound["complete"] is True
    assert bound["records"][0]["source_sha256"] == source_sha256
    assert bound["records"][0]["record"]["method"] == "visual_spatial_v1"


def test_visual_projection_producer_uses_versioned_method_contract() -> None:
    record = START_INTAKE._additional_projection_record(
        "source-000004",
        "projections/source-000004-v1.json",
        b"{}",
        {"elements": [], "relationships": [], "scan_regions": []},
    )

    assert record["method"] == "visual_spatial_v1"
    assert record["gap_count"] == 0


def test_legacy_visual_method_is_qualified_with_explicit_compatibility() -> None:
    source_sha256 = "a" * 64
    projection_sha256 = "b" * 64
    closure = {
        "outcomes": [{
            "source_id": "source-000004",
            "source_sha256": source_sha256,
            "outcome": "projected",
            "projection": {
                "ledger_sequence": 2,
                "id": "projection-source-000004-v1",
                "version": 1,
                "path": "projections/source-000004-v1.json",
                "sha256": projection_sha256,
            },
        }]
    }
    entries = [
        {
            "event": "source_acquired",
            "source": {"id": "source-000004", "sha256": source_sha256},
        },
        {
            "event": "projection_version_created",
            "projection": {
                "id": "projection-source-000004-v1",
                "source_id": "source-000004",
                "version": 1,
                "path": "projections/source-000004-v1.json",
                "sha256": projection_sha256,
                "method": "visual_spatial",
                "coverage": "unassessed",
            },
        },
    ]

    bound = START_INTAKE.source_qualification_binding.bind(closure, entries)
    item = bound["records"][0]
    qualified = START_INTAKE.source_projection_qualification.qualify(
        item,
        b"{}",
        projection_sha256,
        visual_qualification={
            "projection": {"sha256": projection_sha256},
            "remaining_gaps": [],
        },
    )

    compatibility = {
        "legacy_method": "visual_spatial",
        "canonical_method": "visual_spatial_v1",
    }
    assert bound["complete"] is True
    assert item["record"]["method"] == "visual_spatial_v1"
    assert item["record"]["method_compatibility"] == compatibility
    assert qualified["complete"] is True
    assert qualified["qualification"]["method"] == "visual_spatial_v1"
    assert qualified["qualification"]["method_compatibility"] == compatibility


def test_first_layer_terminal_requires_the_exact_current_gap_projection() -> None:
    gap = {
        "source_id": "source-000003",
        "unit": "xl/customData/metrics.xml",
        "reason": "no readable adapter",
    }
    outcome = {
        "source_id": "source-000003",
        "projection_id": "projection-source-000003-v1",
        "projection_sha256": "a" * 64,
        "method": "spreadsheet_ooxml_v1",
        "qualification": "readable_projection_incomplete",
        "gaps": [gap],
    }
    obligation = {
        "id": "clarification-obligation-000001",
        "source_id": gap["source_id"],
        "projection_id": outcome["projection_id"],
        "projection_sha256": outcome["projection_sha256"],
        "method": outcome["method"],
        "qualification": outcome["qualification"],
        "unit": gap["unit"],
        "reason": gap["reason"],
        "gap_sha256": START_INTAKE.effective_first_layer_terminal._digest(gap),
    }
    exact = START_INTAKE.effective_first_layer_terminal.decide(
        {"source_count": 1, "outcomes": [outcome]},
        [obligation],
        [obligation["id"]],
    )
    changed_projection = START_INTAKE.effective_first_layer_terminal.decide(
        {
            "source_count": 1,
            "outcomes": [{**outcome, "projection_sha256": "b" * 64}],
        },
        [obligation],
        [obligation["id"]],
    )

    assert exact["disposition"] == "first_layer_complete"
    assert changed_projection["disposition"] == "clarification_required"
    assert changed_projection["remaining_gaps"] == [gap]


def test_qualification_answers_enter_one_evidence_bound_assessment_round(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    START_INTAKE.run_qualification_admission(work)
    START_INTAKE.request_qualification_question_round(work)
    question_answers = iter([
        "operator_text",
        "What exact readable content belongs to this missing workbook unit?",
    ])
    START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(question_answers),
        output_fn=lambda _message: None,
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_answer="The unit contains the dashboard metric definition.",
    )

    answer_state = json.loads(
        (work / "intake-state.json").read_text(encoding="utf-8")
    )
    projection_path = (
        work
        / answer_state["qualification_question_answers"][0]["projection"]["path"]
    )
    projection_bytes = projection_path.read_bytes()
    ledger_before_changed_evidence = (work / "ledger.jsonl").read_bytes()
    projection_path.write_bytes(projection_bytes + b"changed")
    changed = START_INTAKE.run_clarification_boundary(work)

    assert changed["status"] == "blocked"
    assert "projection bytes" in changed["why"]
    assert (work / "ledger.jsonl").read_bytes() == ledger_before_changed_evidence
    projection_path.write_bytes(projection_bytes)

    requested = START_INTAKE.run_clarification_boundary(work)

    assert requested["boundary"] == "needs_model_interview"
    assert requested["stopped"] == "assessing_qualification_answers"
    assert requested["work"][0]["command"][-1] == (
        "--run-qualification-answer-assessment"
    )
    model_answers = iter([
        "codex",
        "qualification-answer-assessment",
        "yes",
        "resolves_obligation",
        "The answer supplies readable content for the exact missing unit.",
    ])
    assessment_messages: list[str] = []
    assessed = START_INTAKE.run_qualification_answer_assessment(
        work,
        input_fn=lambda _prompt: next(model_answers),
        output_fn=assessment_messages.append,
    )
    ledger_after = (work / "ledger.jsonl").read_bytes()

    assert assessed["status"] == "qualification_answer_assessment_complete"
    assert assessed["assessment"]["assessment_count"] == 1
    assert assessed["assessment"]["resolving_count"] == 1
    assert assessed["assessment"]["assessments"][0]["verdict"] == (
        "resolves_obligation"
    )
    assert len(assessment_messages) == 1
    assert "choose one of" in assessment_messages[0]
    admitted = START_INTAKE.run_clarification_boundary(work)

    assert admitted["boundary"] == "first_layer_complete"
    assert admitted["disposition"] == "first_layer_complete"
    assert admitted["remaining_gap_count"] == 0
    obligation_closure = admitted["qualification_obligation_closure"]
    assert obligation_closure["resolved_count"] == 1
    assert obligation_closure["unresolved_count"] == 0
    assert obligation_closure["resolutions"][0]["obligation_id"] == (
        "clarification-obligation-000001"
    )
    assert obligation_closure["resolutions"][0]["answer_projection_id"] == (
        assessed["assessment"]["assessments"][0]["answer_projection_id"]
    )
    ledger_after_admission = (work / "ledger.jsonl").read_bytes()
    assert ledger_after_admission.startswith(ledger_after)
    assert START_INTAKE.run_clarification_boundary(work) == admitted
    assert (work / "ledger.jsonl").read_bytes() == ledger_after_admission


def test_nonresolving_qualification_answer_admits_exact_followup_obligation(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "reference.xlsx"
    supplied.write_bytes(_representative_workbook_bytes())
    _advance_to_first_source(work)
    START_INTAKE.drive(work, "There is a new intake", REAL_PURPOSE, supplied)
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, project_source=True
    )
    START_INTAKE.drive(
        work, "There is a new intake", REAL_PURPOSE, begin_source_collection=True
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        source_collection_action="finish_sources",
    )
    START_INTAKE.run_source_set_qualification(work)
    START_INTAKE.run_qualification_admission(work)
    START_INTAKE.request_qualification_question_round(work)
    question_answers = iter([
        "operator_text",
        "What exact readable content belongs to this missing workbook unit?",
    ])
    START_INTAKE.run_qualification_question_round(
        work,
        input_fn=lambda _prompt: next(question_answers),
        output_fn=lambda _message: None,
    )
    START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_answer="I do not know what this unit contains.",
    )
    START_INTAKE.run_clarification_boundary(work)
    assessment_answers = iter([
        "codex",
        "qualification-answer-assessment",
        "does_not_resolve_obligation",
        "The answer supplies no readable content for the missing unit.",
    ])
    START_INTAKE.run_qualification_answer_assessment(
        work,
        input_fn=lambda _prompt: next(assessment_answers),
        output_fn=lambda _message: None,
    )
    first_round_journal = (
        work / "qualification-question-round/interview.jsonl"
    ).read_bytes()

    followup = START_INTAKE.run_clarification_boundary(work)

    assert followup["boundary"] == "needs_model_interview"
    assert followup["stopped"] == (
        "formulating_qualification_followup_question_round"
    )
    followup_answers = iter([
        "operator_text",
        "What readable content belongs to this still-missing workbook unit?",
    ])
    prepared = START_INTAKE.run_qualification_followup_question_round(
        work,
        input_fn=lambda _prompt: next(followup_answers),
        output_fn=lambda _message: None,
    )
    ledger_after = (work / "ledger.jsonl").read_bytes()

    assert prepared["status"] == "needs_operator"
    assert prepared["stopped"] == "awaiting_qualification_followup_answers"
    obligation = prepared["question"]["answers_obligation"]
    assert obligation["source_id"] == "source-000003"
    assert obligation["unit"] == "xl/customData/metrics.xml"
    assert obligation["id"] == "qualification-follow-up-000002-000001"
    assert (
        work / "qualification-question-round/interview.jsonl"
    ).read_bytes() == first_round_journal
    assert START_INTAKE.run_clarification_boundary(work) == {
        **prepared,
        "boundary": "needs_operator_answer",
    }
    assert (work / "ledger.jsonl").read_bytes() == ledger_after

    answered = START_INTAKE.drive(
        work,
        "There is a new intake",
        REAL_PURPOSE,
        gap_answer="The missing unit defines the dashboard metric as net revenue divided by transactions.",
    )
    assert answered["status"] == "ready_for_qualification_assessment"
    state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    assert state["qualification_round_number"] == 2
    assert [item["round"] for item in state["qualification_rounds"]] == [1]
    assert state["qualification_rounds"][0]["answers"][0]["submission"][
        "value"
    ] == "I do not know what this unit contains."
    assert len(state["qualification_followup_answers"]) == 1

    assessment_request = START_INTAKE.run_clarification_boundary(work)
    assert assessment_request["boundary"] == "needs_model_interview"
    assert assessment_request["stopped"] == "assessing_qualification_answers"
    followup_assessment_answers = iter([
        "codex",
        "qualification-answer-assessment",
        "resolves_obligation",
        "The follow-up answer supplies readable logic for the exact missing unit.",
    ])
    assessed = START_INTAKE.run_qualification_answer_assessment(
        work,
        input_fn=lambda _prompt: next(followup_assessment_answers),
        output_fn=lambda _message: None,
    )
    assert assessed["assessment"]["resolving_count"] == 1

    terminal = START_INTAKE.run_clarification_boundary(work)
    assert terminal["boundary"] == "first_layer_complete"
    assert terminal["remaining_gap_count"] == 0
    assert terminal["qualification_obligation_closure"][
        "resolved_obligation_ids"
    ] == ["qualification-follow-up-000002-000001"]
    final_ledger = (work / "ledger.jsonl").read_bytes()
    state_path = work / "intake-state.json"
    final_state = state_path.read_bytes()
    terminal_state = json.loads(final_state)
    active_answer = terminal_state["qualification_question_answers"][0]
    ledger_entries = [
        json.loads(line)
        for line in final_ledger.decode("utf-8").splitlines()
        if line.strip()
    ]
    original_source = next(
        entry["source"]
        for entry in ledger_entries
        if isinstance(entry.get("source"), dict)
        and entry["source"].get("id") == "source-000003"
    )
    original_projection = next(
        outcome["projection"]
        for outcome in terminal_state["effective_first_layer_terminal"][
            "source_projection_closure"
        ]["outcomes"]
        if outcome["source_id"] == "source-000003"
    )
    for relative_path in (
        original_source.get("path", original_source.get("stored_path")),
        original_projection["path"],
        active_answer["source"]["path"],
        active_answer["projection"]["path"],
    ):
        evidence_path = work / relative_path
        evidence_bytes = evidence_path.read_bytes()
        evidence_path.write_bytes(evidence_bytes + b"changed")
        changed_evidence = START_INTAKE.run_clarification_boundary(work)
        assert changed_evidence["status"] == "blocked"
        assert "changed" in changed_evidence["stopped"]
        assert (work / "ledger.jsonl").read_bytes() == final_ledger
        evidence_path.write_bytes(evidence_bytes)
    changed_state = json.loads(final_state)
    changed_state["qualification_rounds"][0]["qualification_admission"][
        "clarification_obligations"
    ][0]["unit"] = "changed-unit"
    state_path.write_text(json.dumps(changed_state, sort_keys=True) + "\n")
    changed = START_INTAKE.run_clarification_boundary(work)
    assert changed["status"] == "blocked"
    assert "terminal" in changed["stopped"]
    assert (work / "ledger.jsonl").read_bytes() == final_ledger
    state_path.write_bytes(final_state)
    assert START_INTAKE.run_clarification_boundary(work) == terminal
    assert (work / "ledger.jsonl").read_bytes() == final_ledger
