from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
CASES = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01"
CALENDAR_CASES = ROOT / "Tasks/critique-machinery/atom-03/cases"
NO_REFERENCE = "The frozen test case supplies no professional benchmark page."
NO_UPSTREAM = "The frozen test case supplies no upstream producer material."


def load_module():
    spec = importlib.util.spec_from_file_location("critique_machinery", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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

    def fake_reader(root, source_context, focus, selected, lenses, evidence_root=None, upstream_sources=None):
        evidence_roots.append(evidence_root)
        return [{"lens": lenses[0], "verdict": "clear", "quote": quote}]

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

    def fake_reader(root, source_context, focus, unit, lenses, evidence_root=None, upstream_sources=None):
        calls.append((unit["unit_id"], tuple(lenses), evidence_root))
        quote = module.collapsed(unit["text"])[:120]
        return [{"lens": lens, "verdict": "clear", "quote": quote} for lens in lenses]

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
    assert opening["not_applicable_count"] == 50
    assert opening["benchmark_no_reference_count"] == 25
    assert opening["upstream_no_source_count"] == 25
    assert opening["upstream_no_source_reason"] == reason

    calls = []

    def fake_reader(root, source_context, focus, unit, lenses, evidence_root=None, upstream_sources=None):
        calls.append(tuple(lenses))
        quote = module.collapsed(unit["text"])[:120]
        return [{"lens": lens, "verdict": "clear", "quote": quote} for lens in lenses]

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
    assert refused["status"] == "refused"
    assert refused["outcome"] == "recording-refusal"
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

    def fake_reader(root, source_context, focus, unit, lenses, evidence_root=None, upstream_sources=None):
        assert upstream_sources and upstream_sources[0]["source_id"] == "roadmap"
        quote = module.collapsed(unit["text"])[:120]
        judgments = []
        for lens in lenses:
            verdict = (
                "revise"
                if unit["unit_id"] == first_unit
                and lens == "upstream-trace"
                and evidence_root.name == "reader-1"
                else "clear"
            )
            judgments.append({"lens": lens, "verdict": verdict, "quote": quote})
        return judgments

    monkeypatch.setattr(module, "_reader_judgments", fake_reader)
    result = module.read_run(work)
    assert result["status"] == "complete"
    assert result["unjudged_count"] == 0
    assert result["refused_count"] == 1
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
    assert opening["cell_count"] == 175
    assert opening["unjudged_count"] == 150
    assert opening["not_applicable_count"] == 25
    assert opening["benchmark_no_reference_count"] == 25
    assert opening["benchmark_no_reference_reason"] == reason
    calls = []

    def fake_reader(root, source_context, focus, unit, lenses, evidence_root=None, upstream_sources=None):
        calls.append(tuple(lenses))
        quote = module.collapsed(unit["text"])[:120]
        return [{"lens": lens, "verdict": "clear", "quote": quote} for lens in lenses]

    monkeypatch.setattr(module, "_reader_judgments", fake_reader)
    result = module.read_run(work)
    assert result["status"] == "complete"
    assert result["judged_count"] == 150
    assert result["not_applicable_count"] == 25
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
