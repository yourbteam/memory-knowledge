from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
CASES = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01"
CALENDAR_CASES = ROOT / "Tasks/critique-machinery/atom-03/cases"
NO_REFERENCE = "The frozen test case supplies no professional benchmark page."
NO_UPSTREAM = "The frozen test case supplies no upstream producer material."
FROZEN_V3 = ROOT / "Tasks/critique-machinery/atom-11/frozen-red"


def load_module():
    spec = importlib.util.spec_from_file_location("critique_machinery", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def copy_frozen_v3(module, tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks/run"
    shutil.copytree(FROZEN_V3 / "run", work)
    for path in [work, *work.rglob("*")]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    return work


def reset_v3_owner_rulings(module, work: Path) -> None:
    matrix_path = work / "matrix.json"
    matrix = json.loads(matrix_path.read_text())
    for cell in matrix["cells"]:
        if cell.get("outcome") != "owner-resolved":
            continue
        for key in ("owner_ruling", "owner_ruling_history", "resolved_verdict"):
            cell.pop(key, None)
        cell["outcome"] = module._reader_outcome(cell)
        cell["status"] = "judged" if cell["outcome"].startswith("agreement-") else "unresolved"
    matrix_path.write_bytes(module.canonical(matrix))
    (work / "owner-rulings.json").unlink(missing_ok=True)
    module.owner_queue(work)


def reset_v3_cell(module, work: Path, cell_id: str) -> dict:
    manifest = json.loads((work / "unit-manifest.json").read_text())
    matrix_path = work / "matrix.json"
    matrix = json.loads(matrix_path.read_text())
    cell = next(item for item in matrix["cells"] if item["cell_id"] == cell_id)
    claims = {
        seat: {
            "verdict": reader.get("verdict"),
            "quote": reader.get("quote"),
            "source_id": reader.get("source_id"),
            "source_quote": reader.get("source_quote"),
            **({"intake": reader["intake"]} if reader.get("intake") else {}),
        }
        for seat, reader in cell["readers"].items()
    }
    replacement = next(
        item for item in module.build_matrix(manifest)["cells"] if item["cell_id"] == cell_id
    )
    matrix["cells"][matrix["cells"].index(cell)] = replacement
    matrix_path.write_bytes(module.canonical(matrix))
    return claims


def fake_valid_result(module, lenses, judgments, evidence_root):
    batch_id = evidence_root.parents[1].name
    seat = evidence_root.parent.name
    intake = {
        "schema_version": 1,
        "request_id": f"{batch_id}::{seat}",
        "batch_id": batch_id,
        "seat": seat,
        "attempt": 1,
        "outcome": "valid",
        "lenses": list(lenses),
        "evidence_path": str(evidence_root),
        "reply_bytes": 1,
        "reply_sha256": "test-double",
        "exit_code": 0,
    }
    return {"outcome": "valid", "judgments": judgments, "intake": intake}


def test_real_pages_build_exact_fixed_lens_matrix(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    for case, key in (
        ("btm-roadmap", "context.up.cd_s_002.tactical_roadmap"),
        ("viv-scorecard", "context.up.cd_s_002.measurement_framework"),
    ):
        source = CASES / case
        work = repo / "Tasks" / case
        status, manifest = module.open_run(
            source / "page.md", source / "state.json", key, work,
            no_reference=NO_REFERENCE, no_upstream=NO_UPSTREAM,
        )
        assert status == "opened"
        matrix = json.loads((work / "matrix.json").read_text())
        assert matrix["lenses"] == list(module.LENSES)
        assert len(matrix["cells"]) == len(manifest["units"]) * len(module.LENSES)
        assert module.matrix_status(work)["status"] == "partial"


def test_every_reporting_route_refuses_partial_matrix(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    source = CASES / "btm-roadmap"
    work = repo / "Tasks" / "run"
    module.open_run(
        source / "page.md",
        source / "state.json",
        "context.up.cd_s_002.tactical_roadmap",
        work,
        no_reference=NO_REFERENCE,
        no_upstream=NO_UPSTREAM,
    )
    matrix = json.loads((work / "matrix.json").read_text())
    matrix["cells"][0]["status"] = "judged"
    (work / "matrix.json").write_bytes(module.canonical(matrix))
    status = module.matrix_status(work)
    assert status["status"] == "partial"
    assert status["unjudged_count"] == status["cell_count"] - status["not_applicable_count"] - 1
    for route in ("cell", "report", "document"):
        with pytest.raises(module.Refusal, match="matrix cells are unjudged"):
            module.reporting_route(work, route, matrix["cells"][0]["cell_id"])


def test_judgment_requires_fixed_verdict_and_exact_unit_quote(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    source = CASES / "btm-roadmap"
    work = repo / "Tasks" / "run"
    _, manifest = module.open_run(
        source / "page.md",
        source / "state.json",
        "context.up.cd_s_002.tactical_roadmap",
        work,
        no_reference=NO_REFERENCE,
        no_upstream=NO_UPSTREAM,
    )
    unit = next(unit for unit in manifest["units"] if len(module.collapsed(unit["text"])) >= 25)
    cell_id = f"{unit['unit_id']}::buyer-read"
    with pytest.raises(module.Refusal, match="choose exactly one"):
        module.record_judgment(work, cell_id, "looks-good", unit["text"][:80])
    with pytest.raises(module.Refusal, match="not present"):
        module.record_judgment(work, cell_id, "revise", "invented evidence that is absent from this real unit")
    quote = module.collapsed(unit["text"])[5:90]
    recorded = module.record_judgment(work, cell_id, "revise", quote.replace(" ", "\n", 1))
    assert recorded["readers"]["reader-1"]["quote"] == quote
    assert recorded["readers"]["reader-1"]["verdict"] == "revise"
    with pytest.raises(module.Refusal, match="already has"):
        module.record_judgment(work, cell_id, "clear", quote)


def test_blind_reader_outcomes_remain_distinct(tmp_path: Path) -> None:
    module = load_module()
    source = CASES / "btm-roadmap"

    def opened(name: str):
        repo = tmp_path / name
        (repo / ".git").mkdir(parents=True)
        work = repo / "Tasks" / "run"
        _, manifest = module.open_run(
            source / "page.md", source / "state.json", "context.up.cd_s_002.tactical_roadmap", work,
            no_reference=NO_REFERENCE,
            no_upstream=NO_UPSTREAM,
        )
        unit = next(unit for unit in manifest["units"] if len(module.collapsed(unit["text"])) >= 25)
        return work, f"{unit['unit_id']}::buyer-read", module.collapsed(unit["text"])[5:90]

    work, cell, quote = opened("agreement-defect")
    module.record_reader(work, cell, "reader-1", "revise", quote)
    assert module.record_reader(work, cell, "reader-2", "revise", quote)["outcome"] == "agreement-defect"

    work, cell, quote = opened("agreement-clear")
    module.record_reader(work, cell, "reader-1", "clear", quote)
    assert module.record_reader(work, cell, "reader-2", "clear", quote)["outcome"] == "agreement-clear"

    work, cell, quote = opened("disagreement")
    module.record_reader(work, cell, "reader-1", "revise", quote)
    result = module.record_reader(work, cell, "reader-2", "clear", quote)
    assert result["outcome"] == "disagreement"
    assert result["status"] == "unresolved"

    work, cell, quote = opened("no-answer")
    assert module.record_reader(work, cell, "reader-1", "no-answer", None)["outcome"] == "no-answer"

    work, cell, quote = opened("without-words")
    result = module.record_reader(work, cell, "reader-1", "reject", None)
    assert result["outcome"] == "defect-without-words"
    assert result["status"] == "unresolved"


def test_read_cell_runs_two_separate_blind_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks" / "run"
    source = CASES / "btm-roadmap"
    _, manifest = module.open_run(
        source / "page.md", source / "state.json", "context.up.cd_s_002.tactical_roadmap", work,
        no_reference=NO_REFERENCE,
        no_upstream=NO_UPSTREAM,
    )
    unit = next(unit for unit in manifest["units"] if len(module.collapsed(unit["text"])) >= 25)
    cell_id = f"{unit['unit_id']}::buyer-read"
    quote = module.collapsed(unit["text"])[5:90]
    evidence_roots = []

    def fake_reader(
        root, source_context, focus, selected, lenses, evidence_root=None, upstream_sources=None,
        batch_id=None, seat=None, attempt=1,
    ):
        evidence_roots.append(evidence_root)
        judgments = [{"lens": lenses[0], "verdict": "clear", "quote": quote}]
        return fake_valid_result(module, lenses, judgments, evidence_root)

    monkeypatch.setattr(module, "_reader_judgments", fake_reader)
    result = module.read_cell(work, cell_id)
    assert result["outcome"] == "agreement-clear"
    assert len(evidence_roots) == 2
    assert evidence_roots[0] != evidence_roots[1]


def test_upstream_trace_requires_registered_exact_source_words(tmp_path: Path) -> None:
    module = load_module()

    for case, quote in (
        (
            "calendar-red",
            "Twelve-month corporate calendar showing major moments (results announcements, investor days, AGM, sustainability report publication, executive appearances, signature events, anticipated regulatory milestones), plus always-on activity.",
        ),
        (
            "calendar-green",
            "The 12-month content calendar balanced Hero/Hub/Hygiene, showing the white space.",
        ),
    ):
        repo = tmp_path / case
        (repo / ".git").mkdir(parents=True)
        work = repo / "Tasks" / "run"
        source = CALENDAR_CASES / case
        _, manifest = module.open_run(
            source / "page.md", source / "state.json", "context.up.cd_s_002.execution_toolkit", work,
            no_reference=NO_REFERENCE,
            upstream_sources=[(
                "execution-guide",
                source / "state.json",
                "context.up.cd_s_002.source_document_packet",
            )],
        )
        unit = next(unit for unit in manifest["units"] if "editorial calendar" in unit["text"].casefold())
        cell_id = f"{unit['unit_id']}::upstream-trace"
        unit_quote = module.collapsed(unit["text"])[:100]
        with pytest.raises(module.Refusal, match="has no producer evidence"):
            module.record_reader(work, cell_id, "reader-1", "revise", unit_quote)
        with pytest.raises(module.Refusal, match="already registered"):
            module.register_source(
                work,
                "execution-guide",
                source / "state.json",
                "context.up.cd_s_002.source_document_packet",
            )
        with pytest.raises(module.Refusal, match="not an exact"):
            module.record_trace(work, cell_id, "execution-guide", "invented upstream requirement words")
        trace = module.record_trace(work, cell_id, "execution-guide", quote)
        assert trace["quote"] == quote
        recorded = module.record_reader(work, cell_id, "reader-1", "revise", unit_quote)
        assert recorded["upstream_trace"]["source_id"] == "execution-guide"


def test_benchmark_requires_exact_words_from_both_registered_sides(tmp_path: Path) -> None:
    module = load_module()
    reference_page = CALENDAR_CASES / "calendar-green/page.md"
    reference_quote = next(
        line for line in reference_page.read_text().splitlines() if line.startswith("| Month 11 |")
    )

    for case, verdict in (("calendar-red", "revise"), ("calendar-green", "clear")):
        repo = tmp_path / case
        (repo / ".git").mkdir(parents=True)
        work = repo / "Tasks" / "run"
        source = CALENDAR_CASES / case
        _, manifest = module.open_run(
            source / "page.md", source / "state.json", "context.up.cd_s_002.execution_toolkit", work,
            reference_id="complete-calendar", reference_page=reference_page,
            no_upstream=NO_UPSTREAM,
        )
        unit = next(unit for unit in manifest["units"] if "editorial calendar" in unit["text"].casefold())
        cell_id = f"{unit['unit_id']}::benchmark-vs-reference"
        delivered_quote = next(
            line for line in unit["text"].splitlines() if line.startswith("| Month 12 |")
        )
        if verdict == "revise":
            with pytest.raises(module.Refusal, match="has no paired evidence"):
                module.record_reader(work, cell_id, "reader-1", verdict, module.collapsed(delivered_quote))
        with pytest.raises(module.Refusal, match="already registered"):
            module.register_reference(work, "complete-calendar", reference_page)
        with pytest.raises(module.Refusal, match="reference benchmark quote"):
            module.record_benchmark(
                work, cell_id, "complete-calendar", delivered_quote, "invented professional reference words"
            )
        benchmark = module.record_benchmark(
            work, cell_id, "complete-calendar", delivered_quote, reference_quote
        )
        assert benchmark["reference_id"] == "complete-calendar"
        assert benchmark["delivered_quote"] == module.collapsed(delivered_quote)
        assert benchmark["reference_quote"] == module.collapsed(reference_quote)
        recorded = module.record_reader(
            work, cell_id, "reader-1", verdict, module.collapsed(delivered_quote)
        )
        assert recorded["benchmark"]["strategy"] == "paired-exact-evidence"


def test_owner_queue_blocks_full_btm_document_until_exact_ruling(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks" / "run"
    source = CASES / "btm-roadmap"
    _, manifest = module.open_run(
        source / "page.md", source / "state.json", "context.up.cd_s_002.tactical_roadmap", work,
        no_reference=NO_REFERENCE,
        no_upstream=NO_UPSTREAM,
    )
    matrix = json.loads((work / "matrix.json").read_text())
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    disputed_id = next(cell["cell_id"] for cell in matrix["cells"] if cell["lens"] == "buyer-read")
    for cell in matrix["cells"]:
        if cell["status"] == "not-applicable":
            continue
        quote = module.collapsed(units[cell["unit_id"]]["text"])[:120]
        first = "revise" if cell["cell_id"] == disputed_id else "clear"
        module.record_reader(work, cell["cell_id"], "reader-1", first, quote)
        module.record_reader(work, cell["cell_id"], "reader-2", "clear", quote)
    status = module.matrix_status(work)
    assert status["unjudged_count"] == 0
    assert status["owner_queue_count"] == 1
    question = module.owner_queue(work)["question"]
    assert question["cell_id"] == disputed_id
    with pytest.raises(module.Refusal, match="owner questions remain open"):
        module.reporting_route(work, "document")
    with pytest.raises(module.Refusal, match="was not offered"):
        module.answer_owner(work, question["decision_id"], "average", "machine should decide")
    owner_words = "The owners and the calendar are a person's to approve, and no owner is recorded."
    recorded = module.answer_owner(work, question["decision_id"], "revise", owner_words)
    assert recorded["ruling"]["because"] == owner_words
    corrected_words = "Revise because execution approval remains distinct from platform approval."
    corrected = module.correct_owner(work, question["decision_id"], "revise", corrected_words)
    assert corrected["history_count"] == 1
    refreshed = json.loads((work / "matrix.json").read_text())
    corrected_cell = next(cell for cell in refreshed["cells"] if cell["cell_id"] == disputed_id)
    assert corrected_cell["owner_ruling_history"][0]["because"] == owner_words
    assert corrected_cell["owner_ruling"]["because"] == corrected_words
    output = work / "located-defects.md"
    result = module.reporting_route(work, "document", str(output))
    assert result["status"] == "complete"
    assert result["cells"] == len(manifest["units"]) * len(module.LENSES)
    document = output.read_text()
    assert corrected_words in document
    assert disputed_id in document
    assert module.owner_queue(work)["status"] == "empty"


def test_read_run_batches_each_unit_and_blind_seat_then_completes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks" / "run"
    source = CASES / "btm-roadmap"
    _, manifest = module.open_run(
        source / "page.md", source / "state.json", "context.up.cd_s_002.tactical_roadmap", work,
        no_reference=NO_REFERENCE,
        no_upstream=NO_UPSTREAM,
    )
    calls = []

    def fake_reader(
        root, source_context, focus, unit, lenses, evidence_root=None, upstream_sources=None,
        batch_id=None, seat=None, attempt=1,
    ):
        calls.append((unit["unit_id"], tuple(lenses), evidence_root))
        quote = module.collapsed(unit["text"])[:120]
        judgments = [{"lens": lens, "verdict": "clear", "quote": quote} for lens in lenses]
        return fake_valid_result(module, lenses, judgments, evidence_root)

    monkeypatch.setattr(module, "_reader_judgments", fake_reader)
    result = module.read_run(work)
    assert result["status"] == "complete"
    assert result["reader_calls"] == len(manifest["units"]) * 2
    assert len(calls) == len(manifest["units"]) * 2
    assert all("benchmark-vs-reference" not in lenses for _, lenses, _ in calls)
    assert module.read_run(work)["reader_calls"] == 0


def test_open_requires_exactly_one_benchmark_source_declaration(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    source = CASES / "btm-roadmap"
    arguments = (
        source / "page.md",
        source / "state.json",
        "context.up.cd_s_002.tactical_roadmap",
        repo / "Tasks" / "run",
    )
    with pytest.raises(module.Refusal, match="requires exactly one"):
        module.open_run(*arguments)
    with pytest.raises(module.Refusal, match="received both"):
        module.open_run(
            *arguments,
            reference_id="complete-calendar",
            reference_page=CALENDAR_CASES / "calendar-green/page.md",
            no_reference=NO_REFERENCE,
        )
    with pytest.raises(module.Refusal, match="add --reference-page"):
        module.open_run(*arguments, reference_id="complete-calendar")
    with pytest.raises(module.Refusal, match="non-empty recorded reason"):
        module.open_run(*arguments, no_reference="   ")


def test_open_requires_exactly_one_upstream_source_declaration(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    source = CASES / "btm-roadmap"
    arguments = (
        source / "page.md",
        source / "state.json",
        "context.up.cd_s_002.tactical_roadmap",
        repo / "Tasks" / "run",
    )
    with pytest.raises(module.Refusal, match="upstream-source declaration"):
        module.open_run(*arguments, no_reference=NO_REFERENCE)
    with pytest.raises(module.Refusal, match="both producer sources"):
        module.open_run(
            *arguments,
            no_reference=NO_REFERENCE,
            upstream_sources=[(
                "roadmap",
                source / "state.json",
                "context.up.cd_s_002.tactical_roadmap",
            )],
            no_upstream=NO_UPSTREAM,
        )
    with pytest.raises(module.Refusal, match="non-empty recorded reason"):
        module.open_run(*arguments, no_reference=NO_REFERENCE, no_upstream="   ")


def test_no_upstream_is_visible_terminal_state_and_never_launched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks" / "run"
    source = CASES / "btm-roadmap"
    reason = "No producer material survives for this delivered page"
    _, manifest = module.open_run(
        source / "page.md",
        source / "state.json",
        "context.up.cd_s_002.tactical_roadmap",
        work,
        no_reference=NO_REFERENCE,
        no_upstream=reason,
    )
    opening = module.matrix_status(work)
    assert opening["not_applicable_count"] == 75  # 25 no-reference, 25 no-upstream, 25 no-profile (Atom 18)
    assert opening["benchmark_no_reference_count"] == 25
    assert opening["upstream_no_source_count"] == 25
    assert opening["upstream_no_source_reason"] == reason

    calls = []

    def fake_reader(
        root, source_context, focus, unit, lenses, evidence_root=None, upstream_sources=None,
        batch_id=None, seat=None, attempt=1,
    ):
        calls.append(tuple(lenses))
        quote = module.collapsed(unit["text"])[:120]
        judgments = [{"lens": lens, "verdict": "clear", "quote": quote} for lens in lenses]
        return fake_valid_result(module, lenses, judgments, evidence_root)

    monkeypatch.setattr(module, "_reader_judgments", fake_reader)
    result = module.read_run(work)
    assert result["status"] == "complete"
    assert result["judged_count"] == 125
    assert all("upstream-trace" not in lenses for lenses in calls)
    upstream_cell = next(
        cell for cell in json.loads((work / "matrix.json").read_text())["cells"]
        if cell["lens"] == "upstream-trace"
    )
    assert module.read_cell(work, upstream_cell["cell_id"])["status"] == "not-applicable"
    with pytest.raises(module.Refusal, match="No reader judgment"):
        module.record_reader(work, upstream_cell["cell_id"], "reader-1", "clear", manifest["units"][0]["text"])
    output = work / "findings.md"
    module.reporting_route(work, "document", str(output))
    assert f"Not applicable — {reason}" in output.read_text()


def test_atomic_cell_recording_contains_refusal_and_preserves_siblings(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks" / "run"
    source = CASES / "btm-roadmap"
    _, manifest = module.open_run(
        source / "page.md",
        source / "state.json",
        "context.up.cd_s_002.tactical_roadmap",
        work,
        no_reference=NO_REFERENCE,
        upstream_sources=[(
            "roadmap",
            source / "state.json",
            "context.up.cd_s_002.tactical_roadmap",
        )],
    )
    unit = next(unit for unit in manifest["units"] if len(module.collapsed(unit["text"])) >= 25)
    quote = module.collapsed(unit["text"])[:120]
    upstream_id = f"{unit['unit_id']}::upstream-trace"
    refused = module.record_cell_readers(
        work,
        upstream_id,
        {
            "reader-1": {"verdict": "revise", "quote": quote},
            "reader-2": {"verdict": "clear", "quote": quote},
        },
    )
    assert refused["status"] == "unresolved"
    assert refused["outcome"] == "claim-without-grounded-words"
    assert set(refused["readers"]) == set(module.READER_SEATS)
    assert refused["readers"]["reader-1"]["verdict"] == "revise"
    assert "has no producer evidence" in refused["recording_refusal"]["failures"][0]["reason"]

    sibling_id = f"{unit['unit_id']}::buyer-read"
    sibling = module.record_cell_readers(
        work,
        sibling_id,
        {
            seat: {"verdict": "clear", "quote": quote}
            for seat in module.READER_SEATS
        },
    )
    assert sibling["outcome"] == "agreement-clear"
    status = module.matrix_status(work)
    assert status["refused_count"] == 1
    assert status["owner_queue_count"] == 1
    assert status["half_recorded_count"] == 0


def test_atomic_upstream_defect_records_exact_named_source_words(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks" / "run"
    source = CALENDAR_CASES / "calendar-red"
    _, manifest = module.open_run(
        source / "page.md",
        source / "state.json",
        "context.up.cd_s_002.execution_toolkit",
        work,
        no_reference=NO_REFERENCE,
        upstream_sources=[(
            "execution-guide",
            source / "state.json",
            "context.up.cd_s_002.source_document_packet",
        )],
    )
    unit = next(unit for unit in manifest["units"] if "editorial calendar" in unit["text"].casefold())
    quote = module.collapsed(unit["text"])[:120]
    source_quote = (
        "Twelve-month corporate calendar showing major moments (results announcements, investor days, AGM, "
        "sustainability report publication, executive appearances, signature events, anticipated regulatory "
        "milestones), plus always-on activity."
    )
    cell = module.record_cell_readers(
        work,
        f"{unit['unit_id']}::upstream-trace",
        {
            "reader-1": {
                "verdict": "revise",
                "quote": quote,
                "source_id": "execution-guide",
                "source_quote": source_quote,
            },
            "reader-2": {"verdict": "clear", "quote": quote},
        },
    )
    assert cell["status"] == "unresolved"
    assert cell["readers"]["reader-1"]["upstream_trace"]["source_id"] == "execution-guide"
    assert cell["readers"]["reader-1"]["upstream_trace"]["quote"] == source_quote
    assert len(cell["readers"]) == 2


def test_read_run_continues_after_one_atomic_cell_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks" / "run"
    source = CASES / "btm-roadmap"
    _, manifest = module.open_run(
        source / "page.md",
        source / "state.json",
        "context.up.cd_s_002.tactical_roadmap",
        work,
        no_reference=NO_REFERENCE,
        upstream_sources=[(
            "roadmap",
            source / "state.json",
            "context.up.cd_s_002.tactical_roadmap",
        )],
    )
    first_unit = manifest["units"][0]["unit_id"]

    def fake_reader(
        root, source_context, focus, unit, lenses, evidence_root=None, upstream_sources=None,
        batch_id=None, seat=None, attempt=1,
    ):
        assert upstream_sources and upstream_sources[0]["source_id"] == "roadmap"
        quote = module.collapsed(unit["text"])[:120]
        judgments = []
        for lens in lenses:
            verdict = (
                "revise"
                if unit["unit_id"] == first_unit
                and lens == "upstream-trace"
                and evidence_root.parent.name == "reader-1"
                else "clear"
            )
            judgments.append({"lens": lens, "verdict": verdict, "quote": quote})
        return fake_valid_result(module, lenses, judgments, evidence_root)

    monkeypatch.setattr(module, "_reader_judgments", fake_reader)
    result = module.read_run(work)
    assert result["status"] == "partial"
    assert result["recording_status"] == "complete"
    assert result["unjudged_count"] == 0
    assert result["refused_count"] == 1
    assert result["owner_queue_count"] == 1
    assert result["half_recorded_count"] == 0
    assert result["judged_count"] == 149
    assert result["recording_refusals"] == [f"{first_unit}::upstream-trace"]
    matrix = json.loads((work / "matrix.json").read_text())
    assert all(
        len(cell["readers"]) == 2
        for cell in matrix["cells"]
        if cell["status"] != "not-applicable"
    )


def test_no_reference_is_visible_terminal_state_and_documented(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks" / "run"
    source = CASES / "btm-roadmap"
    reason = "UP supplies no roadmap-shaped benchmark"
    _, manifest = module.open_run(
        source / "page.md", source / "state.json", "context.up.cd_s_002.tactical_roadmap", work,
        no_reference=reason,
        upstream_sources=[(
            "roadmap",
            source / "state.json",
            "context.up.cd_s_002.tactical_roadmap",
        )],
    )
    opening = module.matrix_status(work)
    assert opening["cell_count"] == 200  # eight lenses since Atom 18; the code lens is not applicable here
    assert opening["unjudged_count"] == 150
    assert opening["not_applicable_count"] == 50  # 25 no-reference plus 25 no-profile (Atom 18)
    assert opening["benchmark_no_reference_count"] == 25
    assert opening["benchmark_no_reference_reason"] == reason
    calls = []

    def fake_reader(
        root, source_context, focus, unit, lenses, evidence_root=None, upstream_sources=None,
        batch_id=None, seat=None, attempt=1,
    ):
        calls.append(tuple(lenses))
        quote = module.collapsed(unit["text"])[:120]
        judgments = [{"lens": lens, "verdict": "clear", "quote": quote} for lens in lenses]
        return fake_valid_result(module, lenses, judgments, evidence_root)

    monkeypatch.setattr(module, "_reader_judgments", fake_reader)
    result = module.read_run(work)
    assert result["status"] == "complete"
    assert result["judged_count"] == 150
    assert result["not_applicable_count"] == 50  # 25 no-reference plus 25 no-profile (Atom 18)
    assert all("benchmark-vs-reference" not in lenses for lenses in calls)
    benchmark_cell = next(
        cell for cell in json.loads((work / "matrix.json").read_text())["cells"]
        if cell["lens"] == "benchmark-vs-reference"
    )
    assert module.read_cell(work, benchmark_cell["cell_id"])["status"] == "not-applicable"
    with pytest.raises(module.Refusal, match="No reader judgment"):
        module.record_reader(work, benchmark_cell["cell_id"], "reader-1", "clear", manifest["units"][0]["text"])
    output = work / "findings.md"
    module.reporting_route(work, "document", str(output))
    assert f"Not applicable — {reason}" in output.read_text()


def test_frozen_legacy_red_run_remains_readable_and_unchanged() -> None:
    module = load_module()
    work = ROOT / "Tasks/critique-machinery/atom-08/frozen-red"
    before = module.digest_file(work / "matrix.json")
    status = module.matrix_status(work)
    assert status["cell_count"] == 175
    assert status["unjudged_count"] == 168
    assert status["not_applicable_count"] == 0
    assert module.digest_file(work / "matrix.json") == before


def test_frozen_atom_09_red_run_remains_readable_and_unchanged() -> None:
    module = load_module()
    work = ROOT / "Tasks/critique-machinery/atom-09/frozen-red"
    before = {
        name: module.digest_file(work / name)
        for name in ("unit-manifest.json", "matrix.json", "sources.json", "read-run.log")
    }
    status = module.matrix_status(work)
    assert status["cell_count"] == 175
    assert status["not_applicable_count"] == 25
    assert status["unjudged_count"] == 145
    assert status["owner_queue_count"] == 5
    assert status["half_recorded_count"] == 5
    assert before == {
        name: module.digest_file(work / name)
        for name in before
    }


FROZEN_ATOM_18 = ROOT / "Tasks/critique-machinery/atom-18/frozen-real"


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


def test_reply_intake_has_five_exclusive_actionable_outcomes() -> None:
    module = load_module()
    lenses = ["buyer-read"]
    schema = module.reader_schema(lenses)
    valid = json.dumps({
        "judgments": [{
            "lens": "buyer-read", "verdict": "clear", "start_line": 1, "end_line": 1,
        }]
    })
    cases = [
        (valid, None, "valid"),
        (f"```json\n{valid}\n```", None, "malformed"),
        ("", None, "empty"),
        (b"", "timeout", "timeout"),
        (b"", "nonzero-exit", "nonzero-exit"),
    ]
    observed = []
    for index, (raw, forced, expected) in enumerate(cases, 1):
        result = module.classify_reader_reply(
            raw,
            schema,
            lenses,
            batch_id=f"batch-{index}",
            seat="reader-1",
            attempt=1,
            evidence_path=f"attempt-{index}",
            forced_outcome=forced,
            process_detail=f"observed {expected}",
            exit_code=7 if forced == "nonzero-exit" else 0,
        )
        observed.append(result["outcome"])
        assert result["outcome"] == expected
        if expected != "valid":
            assert f"batch 'batch-{index}', seat 'reader-1'" in result["intake"]["refusal"]
            assert "Return exactly one JSON object" in result["intake"]["refusal"]
    assert observed == list(module.READER_REPLY_OUTCOMES)


def test_each_client_argv_enforces_its_input_envelope() -> None:
    module = load_module()
    schema = module.reader_schema(["buyer-read"])
    codex = module.build_reader_argv(
        ["codex", "exec"], "/bin/codex", schema, Path("/tmp/schema"), Path("/tmp/reply"),
        Path("/tmp/empty"), "system",
    )
    claude = module.build_reader_argv(
        ["claude", "-p"], "/bin/claude", schema, Path("/tmp/schema"), Path("/tmp/reply"),
        Path("/tmp/empty"), "system",
    )
    assert all(flag in codex for flag in (
        "--ignore-user-config", "--ignore-rules", "--ephemeral", "--sandbox", "--output-schema",
    ))
    assert all(flag in claude for flag in (
        "--setting-sources", "--tools", "--system-prompt", "--json-schema",
        "--strict-mcp-config", "--no-session-persistence",
    ))
    assert claude[claude.index("--setting-sources") + 1] == ""
    assert claude[claude.index("--tools") + 1] == ""


def test_failed_seat_gets_one_retry_and_preserves_both_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks/run"
    _, manifest = module.open_run(
        CASES / "btm-roadmap/page.md",
        CASES / "btm-roadmap/state.json",
        "context.up.cd_s_002.tactical_roadmap",
        work,
        no_reference="No benchmark exists",
        no_upstream="No producer source exists",
    )
    unit = manifest["units"][0]
    cell_id = f"{unit['unit_id']}::buyer-read"
    lenses = ["buyer-read"]
    attempt_one = work / "reader-evidence" / f"batch-{unit['unit_id']}" / "reader-1" / "attempt-001"
    attempt_one.mkdir(parents=True)
    failed = module.classify_reader_reply(
        "", module.reader_schema(lenses), lenses, batch_id=f"batch-{unit['unit_id']}",
        seat="reader-1", attempt=1, evidence_path=str(attempt_one),
    )
    quote = module.collapsed(unit["text"])[:120]
    module.record_cell_readers(
        work,
        cell_id,
        {
            "reader-1": module._claims_from_reader_result(failed, lenses)["buyer-read"],
            "reader-2": {"verdict": "clear", "quote": quote},
        },
    )
    calls = []

    def timeout_again(
        root, source_context, focus, unit, lenses, evidence_root=None, upstream_sources=None,
        batch_id=None, seat=None, attempt=1,
    ):
        calls.append((batch_id, seat, attempt))
        evidence_root.mkdir(parents=True)
        (evidence_root / "reader-intake.json").write_text("{}")
        return module.classify_reader_reply(
            b"", module.reader_schema(lenses), lenses, batch_id=batch_id, seat=seat,
            attempt=attempt, evidence_path=str(evidence_root), forced_outcome="timeout",
            process_detail="test process reached its bound", exit_code=None,
        )

    monkeypatch.setattr(module, "_reader_judgments", timeout_again)
    first = module.retry_failed(work)
    second = module.retry_failed(work)
    assert first["reader_calls"] == 1
    assert second["reader_calls"] == 0
    assert calls == [(f"batch-{unit['unit_id']}", "reader-1", 2)]
    assert module.matrix_status(work)["retry_exhausted_seat_count"] == 1
    assert attempt_one.is_dir()
    assert (attempt_one.parent / "attempt-002").is_dir()


def test_frozen_v3_replies_classify_47_valid_and_3_malformed_without_normalization() -> None:
    module = load_module()
    frozen = ROOT / "Tasks/critique-machinery/atom-10/frozen-red"
    before = module.digest_file(frozen / "matrix.json")
    matrix = json.loads((frozen / "matrix.json").read_text())
    lenses_by_unit = {
        unit_id: [
            cell["lens"] for cell in matrix["cells"]
            if cell["unit_id"] == unit_id and cell["status"] != "not-applicable"
        ]
        for unit_id in {cell["unit_id"] for cell in matrix["cells"]}
    }
    outcomes = []
    failures = {}
    paths = sorted(frozen.glob("reader-evidence/batch-*/reader-*/reader.stdout.txt"))
    for path in paths:
        result_events = [
            event.get("result")
            for event in map(json.loads, path.read_text().splitlines())
            if event.get("type") == "result"
        ]
        assert len(result_events) == 1
        batch_id = path.parents[1].name
        unit_id = batch_id.removeprefix("batch-")
        seat = path.parent.name
        result = module.classify_reader_reply(
            result_events[0], module.reader_schema(lenses_by_unit[unit_id]), lenses_by_unit[unit_id],
            batch_id=batch_id, seat=seat, attempt=1, evidence_path=str(path.parent),
        )
        outcomes.append(result["outcome"])
        if result["outcome"] == "malformed":
            failures[f"{unit_id}/{seat}"] = result["intake"]["refusal"]
    assert len(paths) == 50
    assert outcomes.count("valid") == 47
    assert outcomes.count("malformed") == 3
    assert set(failures) == {
        "u-001-67522c23/reader-2", "u-024-14772212/reader-1", "u-024-14772212/reader-2",
    }
    assert "byte 0" in failures["u-001-67522c23/reader-2"]
    assert "byte 442" in failures["u-024-14772212/reader-1"]
    assert "byte 0" in failures["u-024-14772212/reader-2"]
    assert module.digest_file(frozen / "matrix.json") == before


def test_frozen_v3_short_whole_producer_line_records_and_alteration_reaches_owner(tmp_path: Path) -> None:
    module = load_module()
    target = "u-018-55cd0f78::upstream-trace"
    frozen_hash = module.digest_file(FROZEN_V3 / "run/matrix.json")

    accepted_work = copy_frozen_v3(module, tmp_path, "accepted")
    accepted_claims = reset_v3_cell(module, accepted_work, target)
    accepted = module.record_cell_readers(accepted_work, target, accepted_claims)
    assert accepted["outcome"] == "agreement-defect"
    assert accepted["status"] == "judged"
    assert accepted["readers"]["reader-2"]["upstream_trace"]["quote"] == "Always-on after launch."

    altered_work = copy_frozen_v3(module, tmp_path, "altered")
    altered_claims = reset_v3_cell(module, altered_work, target)
    altered_claims["reader-2"]["source_quote"] = "Always-on after launch!"
    altered = module.record_cell_readers(altered_work, target, altered_claims)
    assert altered["outcome"] == "claim-without-grounded-words"
    assert altered["status"] == "unresolved"
    assert module.TRACE_GROUNDING_RULE in altered["recording_refusal"]["failures"][0]["reason"]
    question = module.owner_queue(altered_work)["question"]
    assert question["cell_id"] == target
    assert set(question["reader_evidence"]) == set(module.READER_SEATS)
    with pytest.raises(module.Refusal, match="owner questions remain open"):
        module.reporting_route(altered_work, "document")
    assert module.answer_owner(
        altered_work, question["decision_id"], "revise", "The exact page words establish the owner-visible defect."
    )["status"] == "recorded"
    assert module.digest_file(FROZEN_V3 / "run/matrix.json") == frozen_hash


def test_derived_open_reproduces_v3_payload_and_six_registered_sources(tmp_path: Path) -> None:
    module = load_module()
    state_path, key, specs, derived = module.derive_open_inputs(FROZEN_V3 / "state.json", "tactical_roadmap")
    expected = [
        {name: source[name] for name in ("source_id", "key", "value_sha256")}
        for source in json.loads((FROZEN_V3 / "run/sources.json").read_text())["sources"]
    ]
    assert key == "context.up.cd_s_002.tactical_roadmap"
    assert derived["sources"] == expected
    assert len(specs) == 6

    repo = tmp_path / "derived"
    (repo / ".git").mkdir(parents=True)
    work = repo / "Tasks/run"
    module.open_run(
        FROZEN_V3 / "page.md", state_path, key, work,
        no_reference="UP supplies no roadmap-shaped benchmark", upstream_sources=specs,
    )
    opened = json.loads((work / "sources.json").read_text())["sources"]
    assert [{name: source[name] for name in ("source_id", "key", "value_sha256")} for source in opened] == expected

    incomplete = tmp_path / "incomplete-state.json"
    state = json.loads((FROZEN_V3 / "state.json").read_text())
    del state["context"]["up"]["cd_s_002"]["measurement_framework"]
    incomplete.write_text(json.dumps(state))
    absent_work = repo / "Tasks/absent"
    with pytest.raises(module.Refusal, match="consumes producer 'measurement_framework'"):
        module.derive_open_inputs(incomplete, "tactical_roadmap")
    assert not absent_work.exists()


def test_bulk_ruling_reproduces_v3_choices_and_marker_atomically(tmp_path: Path) -> None:
    module = load_module()
    owner_words = "Kamen: approved in bulk 2026-09-04"
    work = copy_frozen_v3(module, tmp_path, "bulk")
    reset_v3_owner_rulings(module, work)
    result = module.rule_bulk(work, FROZEN_V3 / "assessment.md", owner_words)
    actual = json.loads((work / "owner-rulings.json").read_text())["rulings"]
    expected = json.loads((FROZEN_V3 / "run/owner-rulings.json").read_text())["rulings"]
    assert result["filed"] == 16
    assert [item["cell_id"] for item in actual] == [item["cell_id"] for item in expected]
    assert [item["choice"] for item in actual] == [item["choice"] for item in expected]
    assert all(item["because"].startswith(owner_words + module.BULK_RULING_MARKER) for item in actual)
    assert module.owner_queue(work)["status"] == "empty"

    refused_work = copy_frozen_v3(module, tmp_path, "bulk-refusal")
    reset_v3_owner_rulings(module, refused_work)
    question = module.owner_queue(refused_work)["question"]
    module.answer_owner(refused_work, question["decision_id"], "clear", "Owner filed this one separately.")
    before = {name: module.digest_file(refused_work / name) for name in ("matrix.json", "owner-rulings.json", "owner-queue.json")}
    with pytest.raises(module.Refusal, match="expected exactly"):
        module.rule_bulk(refused_work, FROZEN_V3 / "assessment.md", owner_words)
    assert before == {name: module.digest_file(refused_work / name) for name in before}


def test_located_disputed_reproduces_v3_hand_digest_line_for_line(tmp_path: Path) -> None:
    module = load_module()
    work = copy_frozen_v3(module, tmp_path, "located")
    reset_v3_owner_rulings(module, work)
    actual = module.located(work, "disputed").splitlines()
    expected = (FROZEN_V3 / "page-v3-located.txt").read_text().splitlines()[3:]
    assert actual == expected
    assert sum(line.startswith("### ") for line in actual) == 20


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
