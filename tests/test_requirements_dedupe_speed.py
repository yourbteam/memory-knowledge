import importlib.util
import itertools
import json
from pathlib import Path
import threading
import time
import pytest

ROOT = Path(__file__).resolve().parents[1] / "skills/requirements-machinery/scripts"


def load():
    spec = importlib.util.spec_from_file_location("speed_dedupe", ROOT / "dedupe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_early_stop_preserves_every_possible_four_vote_verdict(monkeypatch):
    module = load()
    for votes in itertools.product(("YES", "NO", None), repeat=4):
        calls = []
        def ask(*args, **kwargs):
            reply = votes[len(calls)]
            calls.append(reply)
            return reply or "unanswered"
        monkeypatch.setattr(module.interview, "ask_free", ask)
        actual, decision = module.read_pair("alpha beta", "alpha gamma", "reader", (1, 2))
        assert decision == module.verdict(list(votes), module.cover("alpha beta", "alpha gamma"))
        assert actual == list(votes[:len(calls)])
        assert len(calls) == 4 or module._owner_fixed(actual)


def test_interrupted_votes_resume_exact_prefix(monkeypatch, tmp_path):
    module = load()
    calls = []
    def interrupted(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("provider interruption")
        return "YES"
    monkeypatch.setattr(module.interview, "ask_free", interrupted)
    with pytest.raises(RuntimeError, match="provider interruption"):
        module.read_pair("alpha beta", "alpha gamma", "reader", (1, 2), cache_dir=tmp_path)
    record = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert record["votes"] == ["YES", "YES"]
    resumed = []
    monkeypatch.setattr(module.interview, "ask_free", lambda *a, **k: resumed.append(1) or "YES")
    assert module.read_pair("alpha beta", "alpha gamma", "reader", (1, 2), cache_dir=tmp_path) == (["YES"] * 4, "merge")
    assert len(resumed) == 2
    module.read_pair("alpha beta", "alpha gamma", "reader", (1, 2), cache_dir=tmp_path)
    assert len(resumed) == 2


def test_checkpoint_rejects_changed_inputs_and_policy(monkeypatch, tmp_path):
    module = load()
    calls = []
    monkeypatch.setattr(module.interview, "ask_free", lambda *a, **k: calls.append(1) or "NO")
    for command, namespace, a in [("reader", "target", "alpha beta"),
                                  ("different reader", "target", "alpha beta"),
                                  ("reader", "other target", "alpha beta"),
                                  ("reader", "target", "alpha delta")]:
        module.read_pair(a, "alpha gamma", command, (1, 2), cache_dir=tmp_path, namespace=namespace)
    assert len(calls) == 16
    monkeypatch.setattr(module, "ASK", module.ASK + " Changed prompt.")
    module.read_pair("alpha beta", "alpha gamma", "reader", (1, 2), cache_dir=tmp_path, namespace="target")
    assert len(calls) == 20


def test_parallel_pairs_are_bounded_ordered_and_faster(monkeypatch):
    module = load()
    monkeypatch.setattr(module, "code_merges", lambda *a: False)
    monkeypatch.setattr(module, "_jaccard", lambda *a: 1)
    lock = threading.Lock()
    active = peak = 0
    def ask(*args, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.012)
        with lock:
            active -= 1
        return "NO"
    monkeypatch.setattr(module.interview, "ask_free", ask)
    entries = ["alpha", "beta", "gamma", "delta"]
    started = time.monotonic()
    serial = module.judge(entries, "reader", max_workers=1)
    serial_elapsed = time.monotonic() - started
    started = time.monotonic()
    parallel = module.judge(entries, "reader")
    parallel_elapsed = time.monotonic() - started
    assert parallel == serial
    assert 1 < peak <= module.MAX_WORKERS
    assert parallel_elapsed < serial_elapsed * 0.8


def test_same_pair_concurrent_call_reuses_single_paid_result(monkeypatch, tmp_path):
    module = load()
    calls = []
    monkeypatch.setattr(module.interview, "ask_free", lambda *a, **k: calls.append(1) or "YES")
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(module.read_pair, "a", "b", "reader", (1, 2), cache_dir=tmp_path) for _ in range(2)]
        assert [future.result() for future in futures] == [(["YES"] * 4, "merge")] * 2
    assert len(calls) == 4
