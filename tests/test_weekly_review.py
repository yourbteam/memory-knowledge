"""Tests for #7 weekly review orchestrator (stamp bump + consolidation)."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_MOD = Path(__file__).resolve().parent.parent / "working-agreement" / "weekly_review.py"
_spec = importlib.util.spec_from_file_location("weekly_review", _MOD)
wr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wr)


def test_bump_review_stamp():
    src = '<!-- Last reviewed: 2026-06-19 -->\nbody'
    out = wr.bump_review_stamp(src, "2026-06-20")
    assert "<!-- Last reviewed: 2026-06-20 -->" in out
    assert "2026-06-19" not in out
    # idempotent
    assert wr.bump_review_stamp(out, "2026-06-20") == out


def test_bump_review_stamp_noop_when_absent():
    assert wr.bump_review_stamp("no stamp here", "2026-06-20") == "no stamp here"


@pytest.mark.asyncio
async def test_consolidate_best_effort():
    class FakeSession:
        async def call_tool(self, tool, args):
            if tool == "run_integrity_audit_workflow":
                return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps({"status": "success"}))])
            raise RuntimeError("compaction down")

    notes = await wr.consolidate(FakeSession(), ["taggable-server"])
    assert any("run_integrity_audit_workflow[taggable-server]=success" in n for n in notes)
    assert any("run_compaction_workflow[taggable-server]=error" in n for n in notes)  # fail-open
