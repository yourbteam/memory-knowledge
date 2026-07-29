"""The `run` operation of local-workflow-orch-image cannot be dispatched.

Live 2026-07-29: an authorized container recreate died instantly with

    local_workflow_orch_image_harness.py run: error: the following arguments are required: --name

`_prepare_local_image` (sequence_intake_adapters.py:2275-2279) lumps `run` in with the six
subcommands that take `--container`, so it emits `--container <name>`. But `run` takes `--name`
(local_workflow_orch_image_harness.py:658), which is also what the registered sequence document and
every historical caller use. The adapter drifted from the documented contract, not the script.

Effect: the image could be rebuilt but the container could never be recreated through the governed
path, so a rebuilt engine could not be put into service.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sequence_intake_adapters as adapters  # noqa: E402

_REPO = "/Users/kamenkamenov/mcp-agents-workflow"
_ROOTS = {"mcp-agents-workflow": _REPO, "memory-knowledge": "/Users/kamenkamenov/memory-knowledge"}


# Mirrors the adapter's own expected_by_operation map (sequence_intake_adapters.py:2236-2252),
# which validates that the answer set matches the operation exactly.
_FIELDS_BY_OPERATION = {
    "build": {"tag"},
    "run": {"tag", "container", "port", "port_file", "env_file"},
    "copy-code-project": {"container", "code_repository_key", "source_relative_path", "destination"},
    "logs": {"container", "tail"},
    "stop": {"container"},
    "seed-codex-auth": {"container", "keyvault_name"},
    "seed-git-auth": {"container", "keyvault_name", "git_repository_key",
                      "seed_port_file", "seed_timeout_seconds"},
    "probe-codex": {"container"},
}


def _argv(operation, **over):
    all_answers = {
        "operation": operation,
        "source_repository_key": "mcp-agents-workflow",
        "tag": "workflow-orch:local-sequence-check",
        "container": "workflow-orch-local-sequence-check",
        "port": 18083,
        "port_file": None,
        "env_file": "/Users/kamenkamenov/.workflow-orch/workflow-orch-local-real-mk.env",
        "health_location": "port",
        "health_port": 18083,
        "health_port_file": None,
        "timeout_seconds": None,
        "code_repository_key": "memory-knowledge",
        "source_relative_path": "scripts",
        "destination": "/workspace/scripts",
        "tail": None,
        "keyvault_name": "hrness",
        "git_repository_key": "mcp-agents-workflow",
        "seed_port_file": "/private/tmp/seed.port",
        "seed_timeout_seconds": None,
    }
    all_answers.update(over)
    keys = {"operation", "source_repository_key", *_FIELDS_BY_OPERATION[operation]}
    answers = {k: v for k, v in all_answers.items() if k in keys}
    return adapters.ADAPTER_REGISTRY["local-workflow-orch-image"](answers, {}, _ROOTS)["argv"]


def test_run_uses_the_flag_the_script_and_sequence_document_define():
    argv = _argv("run")
    assert "--name" in argv, "run takes --name; emitting --container aborts the recreate"
    assert "--container" not in argv
    assert argv[argv.index("--name") + 1] == "workflow-orch-local-sequence-check"


def test_run_still_carries_tag_port_and_env_file():
    argv = _argv("run")
    for flag in ("--tag", "--port", "--env-file"):
        assert flag in argv


def test_container_subcommands_keep_container():
    """NO REGRESSION: the six operations that really do take --container are untouched."""
    for operation in ("logs", "stop", "seed-codex-auth", "seed-git-auth", "probe-codex",
                      "copy-code-project"):
        argv = _argv(operation)
        assert "--container" in argv, operation
        assert "--name" not in argv, operation
