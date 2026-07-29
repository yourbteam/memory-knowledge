"""blk-af452065311f7f6c0b7ebc6e — a runner-prefixed command cannot be dispatched.

Live 2026-07-29: an AUTHORIZED `local-workflow-orch-image` build aborted with
`prepared-script-source-ambiguous`. The prepared argv is

    ["uv", "run", "python", "<repo>/scripts/local_workflow_orch_image_harness.py", "build", ...]

`_invoked_script` (sequence_intake_launch.py:391-419) resolves the script by stripping a LEADING
interpreter -- python/python3/bash/sh/zsh -- and otherwise looking only at argv[:1]. For a `uv run`
command argv[0] is "uv", so it inspects just that one token, finds no .py/.sh, and ends with ZERO
candidates rather than one. Every sequence whose registered command is invoked through `uv run` is
therefore undispatchable, which blocked the container rebuild.

The exactly-one rule is the point of the guard and must survive: a command naming two scripts is
still ambiguous.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sequence_intake_launch  # noqa: E402

_ROOT = "/Users/kamenkamenov/mcp-agents-workflow"
_SCRIPT = f"{_ROOT}/scripts/local_workflow_orch_image_harness.py"


def _prepared(argv):
    return {"argv": argv, "repository": {"key": "mcp-agents-workflow", "root": _ROOT}}


def test_uv_run_python_script_resolves_the_script():
    """The exact live argv that failed."""
    resolved = sequence_intake_launch._invoked_script(
        _prepared(["uv", "run", "python", _SCRIPT, "build", "--tag", "workflow-orch:local"]))
    assert resolved == Path(_SCRIPT)


def test_uv_run_script_without_interpreter_resolves():
    resolved = sequence_intake_launch._invoked_script(
        _prepared(["uv", "run", _SCRIPT, "build"]))
    assert resolved == Path(_SCRIPT)


def test_plain_interpreter_still_resolves():
    """NO REGRESSION: the shape the guard already handled."""
    resolved = sequence_intake_launch._invoked_script(
        _prepared(["python3", "scripts/scoped_git_publish.py", "--repo", _ROOT]))
    assert resolved == Path(_ROOT) / "scripts/scoped_git_publish.py"


def test_bare_script_still_resolves():
    resolved = sequence_intake_launch._invoked_script(_prepared([_SCRIPT, "build"]))
    assert resolved == Path(_SCRIPT)


def test_a_script_path_in_the_arguments_is_not_mistaken_for_the_invoked_script():
    """The guard inspects the invoked token only, so a script path passed as an ARGUMENT does not
    change what runs. Stripping the runner prefix must preserve that -- it would be wrong to start
    scanning the whole argv, which is how a flag value could hijack the resolved source."""
    resolved = sequence_intake_launch._invoked_script(
        _prepared(["uv", "run", "python", _SCRIPT, "--helper", f"{_ROOT}/scripts/other.py"]))
    assert resolved == Path(_SCRIPT)


def test_no_script_at_all_is_still_rejected():
    with pytest.raises(sequence_intake_launch.SequenceLaunchError, match="prepared-script-source-ambiguous"):
        sequence_intake_launch._invoked_script(_prepared(["docker", "ps"]))
