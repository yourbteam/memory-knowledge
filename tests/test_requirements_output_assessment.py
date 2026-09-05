import importlib.util
import hashlib
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1] / "skills/requirements-machinery/scripts"


def load():
    spec = importlib.util.spec_from_file_location("assess_finished", ROOT / "assess_output.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files(tmp_path, statements=None):
    source = "Capture a measurement expectation in every debrief."
    (tmp_path / "source.txt").write_text(source)
    reference = {"schema_version": 1, "scope": "reference-relative", "target": "debrief",
                 "source": {"path": "source.txt", "sha256": hashlib.sha256(source.encode()).hexdigest()},
                 "duties": [{"id": "measurement", "quote": source}]}
    (tmp_path / "reference.json").write_text(json.dumps(reference))
    items = statements or [source]
    document = "# Requirements — debrief\n\n## The requirements\n\n" + "\n\n".join(f"{i}. {text}\n   *(p.1)*" for i, text in enumerate(items, 1))
    document += "\n\n## Owner rulings (recorded)\n\n- owner-1: keep — recorded reason\n"
    (tmp_path / "document.md").write_text(document)
    return tmp_path / "reference.json", tmp_path / "document.md"


def test_qualified_output_keeps_full_evidence_and_counts(monkeypatch, tmp_path):
    module = load()
    reference, document = files(tmp_path)
    seen = []
    def ask(reader, prompt, choices, **labels):
        seen.append((prompt, labels))
        return "YES", [{"raw_reply": "YES", "accepted": "YES"}]
    monkeypatch.setattr(module.interview, "ask_choice", ask)
    report = module.assess(reference, document, "reader")
    assert report["verdict"] == "qualified"
    assert report["metrics"] == {"coverage": 1, "supported": 1, "duplicate_count": 0, "uncertain_count": 0, "owner_intervention_count": 1}
    assert len(seen) == 4
    assert report["judgments"][0]["seats"][0]["attempts"][0]["raw_reply"] == "YES"
    assert report["reference"]["sha256"] == hashlib.sha256(reference.read_bytes()).hexdigest()


def test_missing_and_unsupported_do_not_qualify(monkeypatch, tmp_path):
    module = load()
    reference, document = files(tmp_path, ["The measurement expectation was not captured."])
    monkeypatch.setattr(module.interview, "ask_choice", lambda *a, **k: ("NO", []))
    report = module.assess(reference, document, "reader")
    assert report["omissions"] == ["measurement"]
    assert report["unsupported_against_reference"] == [1]
    assert report["verdict"] == "needs-attention"


@pytest.mark.parametrize("answers", [("YES", "NO"), ("UNCERTAIN", "UNCERTAIN"), (None, "YES")])
def test_disagreement_and_unanswered_remain_uncertain(monkeypatch, tmp_path, answers):
    module = load()
    reference, document = files(tmp_path)
    monkeypatch.setattr(module.interview, "ask_choice", lambda *a, **k: (answers[k["seat"] - 1], []))
    report = module.assess(reference, document, "reader")
    assert report["metrics"]["uncertain_count"] == 2
    assert report["verdict"] == "needs-attention"


def test_exact_duplicates_are_reported_without_reader_decision(monkeypatch, tmp_path):
    module = load()
    reference, document = files(tmp_path, ["Capture measurement.", "Capture measurement."])
    monkeypatch.setattr(module.interview, "ask_choice", lambda *a, **k: ("YES", []))
    report = module.assess(reference, document, "reader")
    assert report["duplicate_pairs"] == [[1, 2]]
    assert report["judgments"][-1]["by"] == "exact-text"
    assert report["verdict"] == "needs-attention"


def test_source_drift_is_refused_before_reader(monkeypatch, tmp_path):
    module = load()
    reference, document = files(tmp_path)
    (tmp_path / "source.txt").write_text("changed")
    monkeypatch.setattr(module.interview, "ask_choice", lambda *a, **k: pytest.fail("reader spent"))
    with pytest.raises(ValueError, match="source hash"):
        module.assess(reference, document, "reader")


@pytest.mark.parametrize("section", ["", "2. Missing first item", "1. valid\nuntracked text", "1. valid\n## surprise\n2. hidden"])
def test_malformed_inventory_is_refused(section):
    module = load()
    text = "# Requirements — target\n## The requirements\n" + section + "\n## Owner rulings (recorded)\n"
    with pytest.raises(ValueError):
        module.parse_document(text)


def test_long_complete_inventory_and_continuations_reach_both_seats(monkeypatch, tmp_path):
    module = load()
    statement = "Long sentence. " * 1000 + "TAIL DUTY.\n   Continuation duty."
    reference, document = files(tmp_path, [statement])
    seen = []
    monkeypatch.setattr(module.interview, "ask_choice", lambda reader, prompt, choices, **k: (seen.append(prompt) or "YES", []))
    module.assess(reference, document, "reader")
    assert len(seen) == 4
    assert all("TAIL DUTY." in prompt and "Continuation duty." in prompt for prompt in seen)


def test_report_cannot_overwrite_any_input(tmp_path):
    module = load()
    reference, document = files(tmp_path)
    before = document.read_bytes()
    assert module.main(["--reference", str(reference), "--document", str(document), "--report", str(document), "--reader-command", "reader"]) == 3
    assert document.read_bytes() == before


@pytest.mark.parametrize("invalid", [[], None, "reference", 4])
def test_malformed_reference_root_refuses_without_reader(monkeypatch, tmp_path, invalid):
    module = load()
    reference, document = files(tmp_path)
    reference.write_text(json.dumps(invalid))
    monkeypatch.setattr(module.interview, "ask_choice", lambda *a, **k: pytest.fail("reader spent"))
    assert module.main(["--reference", str(reference), "--document", str(document), "--report", str(tmp_path / "report.json"), "--reader-command", "reader"]) == 3
    assert not (tmp_path / "report.json").exists()


def test_independent_jobs_parallel_bounded_with_ordered_results(monkeypatch, tmp_path):
    import threading
    import time
    module = load()
    reference, document = files(tmp_path, ["Capture measurement.", "Record target.", "Name owner."])
    active = peak = 0
    lock = threading.Lock()
    def ask(reader, question, choices, **labels):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return ("NO" if labels["stage"].endswith("duplicate") else "YES"), []
    monkeypatch.setattr(module.interview, "ask_choice", ask)
    report = module.assess(reference, document, "reader")
    assert 1 < peak <= 4
    assert [(row["kind"], row["identity"]) for row in report["judgments"]] == [
        ("coverage", "measurement"), ("support", 1), ("support", 2), ("support", 3),
        ("duplicate", [1, 2]), ("duplicate", [1, 3]), ("duplicate", [2, 3])]
    assert report["assessment_code"]["assessor_sha256"] == hashlib.sha256((ROOT / "assess_output.py").read_bytes()).hexdigest()


def test_summary_reconstructs_accounting_after_judgment_changes(monkeypatch, tmp_path):
    module = load()
    reference, document = files(tmp_path)
    monkeypatch.setattr(module.interview, "ask_choice", lambda *a, **k: ("YES", []))
    report = module.assess(reference, document, "reader")
    assert report["verdict"] == "qualified"
    report["judgments"][0]["decision"] = "NO"
    updated = module.summarize(report)
    assert updated["verdict"] == "needs-attention"
    assert updated["omissions"] == ["measurement"]
    assert updated["metrics"]["coverage"] == 0
    report["judgments"].pop()
    with pytest.raises(ValueError, match="every declared duty, item, and pair"):
        module.summarize(report)


def test_coverage_prompt_requires_prescribed_action_without_inferred_remedy(monkeypatch, tmp_path):
    """Mechanical prompt contract; live reader accuracy is validated separately."""
    module = load()
    reference, document = files(tmp_path, ["The measurement expectation was not captured."])
    prompts = []
    def ask(reader, question, choices, **labels):
        if labels["stage"] == "output-assessment-coverage":
            prompts.append(question)
        return "NO", []
    monkeypatch.setattr(module.interview, "ask_choice", ask)
    report = module.assess(reference, document, "reader")
    assert len(prompts) == 2
    for prompt in prompts:
        assert "actor, required action, object, polarity, frequency, and condition" in prompt
        assert "must explicitly survive" in prompt
        assert "Natural paraphrases are allowed" in prompt
        assert "Do not infer a remedy, future action" in prompt
        assert "past omission or problem does not retain a prescribed action" in prompt
    assert report["omissions"] == ["measurement"]
    assert report["metrics"]["coverage"] == 0
