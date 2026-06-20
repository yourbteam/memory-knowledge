"""Tests for #3 directive Spark — proactive candidate surfacing (never auto-promotes)."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_MOD = Path(__file__).resolve().parent.parent / "working-agreement" / "directive_spark.py"
_spec = importlib.util.spec_from_file_location("directive_spark", _MOD)
ds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ds)


def _result(obj):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(obj))])


def test_items_extraction():
    assert ds._items({"data": [1, 2]}) == [1, 2]
    assert ds._items({"data": {"rows": [{"a": 1}]}}) == [{"a": 1}]
    assert ds._items({"nope": 1}) == []


def test_render_empty_and_nonempty():
    assert "No recurring patterns" in ds.render([])
    out = ds.render([{"repo": "taggable-server", "signal": "get_finding_pattern_summary", "item": {"x": 1}}])
    assert "get_finding_pattern_summary" in out and "taggable-server" in out
    assert "DIRECTIVES.md" in out  # the review-only reminder mentions it, but never writes it


@pytest.mark.asyncio
async def test_gather_applies_frequency_floor_and_fail_open(monkeypatch):
    monkeypatch.setattr(ds, "MIN_FREQ", 2)

    class FakeSession:
        async def call_tool(self, tool, args):
            if tool == "get_finding_pattern_summary":
                return _result({"status": "success", "data": [{"pattern": "hot", "count": 3},
                                                              {"pattern": "rare", "count": 1}]})
            raise RuntimeError("tool down")  # other signals fail-open

    rows = await ds.gather(FakeSession(), "taggable-server")
    pats = [r["item"]["pattern"] for r in rows]
    assert "hot" in pats and "rare" not in pats  # floor drops count<2
    assert all(r["repo"] == "taggable-server" for r in rows)


def test_output_target_is_review_file_not_directives():
    assert ds.OUT.name == "spark-candidates.md"  # never DIRECTIVES.md
