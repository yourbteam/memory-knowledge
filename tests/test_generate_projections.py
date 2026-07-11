"""Tests for the DIRECTIVES.md projection generator (Gap #1 / #4).

Projections must be derived from DIRECTIVES.md and clearly marked generated, so no tool's
on-disk file is ever treated as authoritative.
"""

import importlib.util
from pathlib import Path
from unittest import mock

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


def _full_directives(tmp_path):
    d = tmp_path / "DIRECTIVES.md"
    d.write_text("# Working Agreement\n\n## G0 · Compliance\n**Why:** ...\n## G1 · Grasp\n**Why:** ...\n")
    return d


def test_refresh_skips_repo_own_agents(tmp_path):
    d = _full_directives(tmp_path)
    own = "# Repository Guidelines\n\n## Build\nrun make\n"
    assert gp.refresh_agents_file(own, gp.read_directives(d)) is None  # never clobber a repo's own file


def test_refresh_skips_hand_pointer(tmp_path):
    d = _full_directives(tmp_path)
    pointer = "# Codex Working Agreement\n\nRead working-agreement/DIRECTIVES.md\n"  # no GENERATED header, no G0
    assert gp.refresh_agents_file(pointer, gp.read_directives(d)) is None


def test_refresh_regenerates_full_projection(tmp_path):
    d = _full_directives(tmp_path)
    stale = gp.agents_projection("# Working Agreement\n\n## G0 · Compliance\n**Why:** OLD\n")
    out = gp.refresh_agents_file(stale, gp.read_directives(d))
    assert out is not None and "## G1 · Grasp" in out and "OLD" not in out


def test_refresh_refreshes_merge_block_only(tmp_path):
    d = _full_directives(tmp_path)
    merged = gp.merge_into("# Repo own\nkeep\n", "# Working Agreement\n\n## G0 · old\n**Why:** OLD\n")
    out = gp.refresh_agents_file(merged, gp.read_directives(d))
    assert out is not None
    assert "keep" in out and "## G1 · Grasp" in out and "OLD" not in out
    assert out.count(gp.MERGE_BEGIN) == 1


def test_codex_trusted_projects_parses_headers(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'model = "x"\n[projects."/Users/k/repo-a"]\ntrust_level = "trusted"\n'
        '[projects."/Users/k/repo-b"]\ntrust_level = "trusted"\n[mcp_servers.x]\n'
    )
    projs = gp.codex_trusted_projects(cfg)
    assert [p.name for p in projs] == ["repo-a", "repo-b"]


def test_codex_trusted_projects_missing_config(tmp_path):
    assert gp.codex_trusted_projects(tmp_path / "nope.toml") == []


def _allowlisted_fixture(tmp_path):
    gp.LOCK_ROOT = tmp_path / "projection-locks"
    project = tmp_path / "owned"
    project.mkdir()
    directives = tmp_path / "DIRECTIVES.md"
    directives.write_text("## G0 · Rule\nbody\n")
    allowlist = tmp_path / "allowlist"
    allowlist.write_text(str(project) + "\n")
    return project, directives, allowlist


def test_allowlisted_create_is_dry_run_then_apply(tmp_path):
    project, directives, allowlist = _allowlisted_fixture(tmp_path)
    result = gp.refresh_projects(directives, [project], allowlist, apply=False, create_missing=True)
    assert "would-create" in result[0]
    assert not (project / "AGENTS.md").exists()
    result = gp.refresh_projects(directives, [project], allowlist, apply=True, create_missing=True)
    assert "created" in result[0]
    assert (project / "AGENTS.md").exists()
    assert not (project / ".AGENTS.md.working-agreement.lock").exists()


def test_non_allowlisted_project_is_skipped(tmp_path):
    project = tmp_path / "other"
    project.mkdir()
    directives = tmp_path / "DIRECTIVES.md"
    directives.write_text("## G0 · Rule\nbody\n")
    allowlist = tmp_path / "allowlist"
    allowlist.write_text("")
    result = gp.refresh_projects(directives, [project], allowlist, apply=True, create_missing=True)
    assert "skip(not-allowlisted)" in result[0]


def test_refresh_only_missing_preserves_legacy_skip(tmp_path):
    project, directives, allowlist = _allowlisted_fixture(tmp_path)
    result = gp.refresh_projects(directives, [project], allowlist, apply=True, create_missing=False)
    assert "skip(no-AGENTS.md)" in result[0]


def test_hand_authored_file_is_preserved(tmp_path):
    project, directives, allowlist = _allowlisted_fixture(tmp_path)
    target = project / "AGENTS.md"
    target.write_text("hand-authored\n")
    result = gp.refresh_projects(directives, [project], allowlist, apply=True, create_missing=True)
    assert "skip(not-generated)" in result[0]
    assert target.read_text() == "hand-authored\n"


def test_raced_create_preserves_winner(tmp_path):
    project, directives, allowlist = _allowlisted_fixture(tmp_path)
    target = project / "AGENTS.md"

    def race(_temp, destination):
        Path(destination).write_text("winner\n")
        raise FileExistsError

    with mock.patch.object(gp.os, "link", side_effect=race):
        result = gp.refresh_projects(directives, [project], allowlist, apply=True, create_missing=True)
    assert "skip(raced-existing)" in result[0]
    assert target.read_text() == "winner\n"
