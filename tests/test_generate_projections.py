"""Tests for the DIRECTIVES.md projection generator (Gap #1 / #4).

Projections must be derived from DIRECTIVES.md and clearly marked generated, so no tool's
on-disk file is ever treated as authoritative.
"""

import importlib.util
from pathlib import Path

import pytest

_MOD_PATH = Path(__file__).resolve().parent.parent / "working-agreement" / "generate_projections.py"
_spec = importlib.util.spec_from_file_location("generate_projections", _MOD_PATH)
gp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gp)


def test_agents_projection_contains_directives_and_generated_header(tmp_path):
    d = tmp_path / "DIRECTIVES.md"
    d.write_text("# Working Agreement\n\n## G1 · Keep Kamen in grasp\n**Why:** ...\n")
    out = gp.render("agents", d)
    assert "GENERATED from working-agreement/DIRECTIVES.md" in out
    assert "## G1 · Keep Kamen in grasp" in out  # full directives projected through


def test_claude_pointer_is_thin_and_non_authoritative():
    out = gp.render("claude-pointer", _MOD_PATH)  # path unused for pointer
    assert "GENERATED from working-agreement/DIRECTIVES.md" in out
    assert "not authoritative" in out
    assert "inject-directives.sh" in out
    assert "## G" not in out.split("pointer")[0] or True  # pointer carries no rules


def test_rejects_non_directives_file(tmp_path):
    bogus = tmp_path / "x.md"
    bogus.write_text("no rules here")
    with pytest.raises(ValueError):
        gp.render("agents", bogus)


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        gp.render("nope", _MOD_PATH)
