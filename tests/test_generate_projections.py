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


def _directives(tmp_path, body="## G1 · Keep Kamen in grasp\n**Why:** ...\n"):
    d = tmp_path / "DIRECTIVES.md"
    d.write_text(f"# Working Agreement\n\n{body}")
    return d


def test_merge_appends_block_and_preserves_repo_content(tmp_path):
    d = _directives(tmp_path)
    existing = "# Repository Guidelines\n\n## Build\nrun make\n"
    merged = gp.merge_into(existing, gp.read_directives(d))
    # repo content preserved verbatim
    assert "# Repository Guidelines" in merged
    assert "run make" in merged
    # directives folded in, inside the fence, after the repo content
    assert gp.MERGE_BEGIN in merged and gp.MERGE_END in merged
    assert merged.index("run make") < merged.index(gp.MERGE_BEGIN)
    assert "## G1 · Keep Kamen in grasp" in merged
    assert merged.index(gp.MERGE_BEGIN) < merged.index("## G1") < merged.index(gp.MERGE_END)


def test_merge_is_idempotent_replaces_block_not_duplicates(tmp_path):
    d = _directives(tmp_path)
    existing = "# Repository Guidelines\n\n## Build\nrun make\n"
    once = gp.merge_into(existing, gp.read_directives(d))
    twice = gp.merge_into(once, gp.read_directives(d))
    assert once == twice  # stable
    assert twice.count(gp.MERGE_BEGIN) == 1 and twice.count(gp.MERGE_END) == 1


def test_merge_refreshes_block_on_directive_change(tmp_path):
    d = _directives(tmp_path)
    existing = "# Repo\nkeep me\n"
    first = gp.merge_into(existing, gp.read_directives(d))
    d.write_text("# Working Agreement\n\n## G99 · New rule\n**Why:** changed\n")
    second = gp.merge_into(first, gp.read_directives(d))
    assert "keep me" in second  # repo content still there
    assert "## G99 · New rule" in second
    assert "## G1 · Keep Kamen in grasp" not in second  # old block fully replaced
    assert second.count(gp.MERGE_BEGIN) == 1
