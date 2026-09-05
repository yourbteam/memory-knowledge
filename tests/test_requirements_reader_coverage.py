import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1] / "skills/requirements-machinery/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_relevance_every_seat_reads_tail(monkeypatch):
    module = load("relevance")
    page = "Ordinary background. " * 600 + "MANDATORY evidence at the end."
    seen = []
    def choice(command, question, choices, **kwargs):
        seen.append((kwargs["seat"], question))
        return ("YES" if "MANDATORY" in question else "NO"), [{"raw_first_line": "answer"}]
    monkeypatch.setattr(module.interview, "ask_choice", choice)
    monkeypatch.setattr(module.interview, "ask_quote", lambda *a, **k: ("MANDATORY evidence at the end.", []))
    verdict, seats = module.judge(page, "target", "reader", load("quotecheck"))
    assert verdict == "bears"
    for seat in seats:
        assert seat["coverage"]["complete"]
        assert any("MANDATORY" in question for identity, question in seen if identity == seat["seat"])
        batches = seat["coverage"]["batches"]
        assert batches[0]["start"] == 0
        assert all(a["end"] == b["start"] for a, b in zip(batches, batches[1:]))
        assert batches[-1]["end"] == len("\n".join(module._reflow.units(page, min_chars=1)))


def test_unanswered_batch_never_means_no(monkeypatch):
    module = load("relevance")
    monkeypatch.setattr(module.interview, "ask_choice", lambda *a, **k: (None, []))
    verdict, seats = module.judge("Long source. " * 900, "target", "reader", load("quotecheck"))
    assert verdict == "no-answer"
    assert all(not seat["coverage"]["complete"] for seat in seats)


def test_obligations_all_global_ids_survive_batches(monkeypatch):
    module = load("obligations")
    candidates = [f"Obligation number {i} has its full original words." for i in range(1005)]
    prompts = []
    def ask(command, question, **kwargs):
        prompts.append(question)
        block = question.split("--- NUMBERED LINES ---\n")[1].split("\n--- END ---")[0]
        return "\n".join(line.split(".")[0] for line in block.splitlines())
    monkeypatch.setattr(module.interview, "ask_free", ask)
    receipts = []
    picked = module._ask_one_cut(candidates, "target", "reader", " ".join(candidates), load("quotecheck"), receipts=receipts)
    assert picked == candidates
    assert [i for r in receipts for i in r["unit_ids"]] == list(range(1, 1006))
    assert len(prompts) > 1


@pytest.mark.parametrize("reply", ["", "nonsense", "NONE\n1", "2", "1\ninvalid"])
def test_malformed_obligation_reply_is_not_empty_selection(monkeypatch, reply):
    module = load("obligations")
    monkeypatch.setattr(module.interview, "ask_free", lambda *a, **k: reply)
    with pytest.raises(ValueError):
        module._ask_one_cut(["Required."], "target", "reader", "Required.", load("quotecheck"))


def test_oversized_and_short_units_are_not_hidden():
    module = load("obligations")
    piece = "Yes. " + "x" * 12000
    candidates = module.candidate_units(piece)
    assert any("Yes." in unit for units in candidates.values() for unit in units)
    batches = module.coverage.unit_batches(["x" * 12000, "short"])
    assert batches[0][0]["text"] == "x" * 12000
    assert batches[1][0]["id"] == 2


def test_receipt_rejects_missing_batches_and_changed_source(monkeypatch):
    module = load("relevance")
    monkeypatch.setattr(module.interview, "ask_choice", lambda *a, **k: ("NO", []))
    source = "Background statement. " * 900
    _, seats = module.judge(source, "target", "reader", load("quotecheck"))
    receipt = seats[0]["coverage"]
    assert module.coverage.matches(receipt, source, "target")
    assert not module.coverage.matches(receipt, source + "Changed.", "target")
    assert not module.coverage.matches({**receipt, "batches": receipt["batches"][:-1]}, source, "target")


def test_unit_receipt_rejects_missing_offered_unit(monkeypatch):
    module = load("obligations")
    monkeypatch.setattr(module.interview, "ask_free", lambda *a, **k: "NONE")
    source = "Required one. Required two."
    _, _, cuts = module.extract(source, "target", "reader", load("quotecheck"))
    receipt = module.coverage.receipt(source, "target", [{"cut": name, **cut["coverage"]} for name, cut in cuts.items()])
    assert module.coverage.matches(receipt, source, "target")
    receipt["batches"][0]["batches"][0]["unit_ids"].pop()
    assert not module.coverage.matches(receipt, source, "target")


def test_cover_receipt_happy_path_preserves_every_section_quote(monkeypatch, tmp_path):
    cover = load("cover")
    relevance = load("relevance")
    obligations = load("obligations")
    source = "First required source statement. " + "Background statement. " * 500 + "Last required source statement."
    (tmp_path / "pieces").mkdir()
    (tmp_path / "pieces/p-0001.txt").write_text(source)
    target = "target requirements"
    def choice(command, prompt, choices, **context):
        return "YES", []
    def quote(command, prompt, source_section, checker, **context):
        if "First required" in source_section:
            return "First required source statement.", []
        return "Last required source statement.", []
    monkeypatch.setattr(relevance.interview, "ask_choice", choice)
    monkeypatch.setattr(relevance.interview, "ask_quote", quote)
    monkeypatch.setattr(obligations.interview, "ask_free", lambda *a, **k: "NONE")
    original_load = cover._load
    monkeypatch.setattr(cover, "_load", lambda name: {"relevance": relevance, "obligations": obligations}.get(name) or original_load(name))
    state = {"pieces": [{"id": "p-0001"}]}
    monkeypatch.setattr(cover, "_read", lambda work: state)
    monkeypatch.setattr(cover, "_write", lambda work, value: None)
    assert cover.relevance(tmp_path, target, "reader") == 0
    assert cover.obligations(tmp_path, "reader") == 0
    output = state["obligations"][target]["p-0001"]
    assert any("First required" in text for text in output["obligations"])
    assert any("Last required" in text for text in output["obligations"])
    assert cover._reader_coverage_error(state, target, tmp_path, include_obligations=True) is None
    assert state["obligation_completion"][target]["complete"] is True
