"""Fail-closed tests for client-bound machinery reader launches."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True


def load_policy_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "machinery", ["implementation-machine", "description-machinery", "requirements-machine"],
)
@pytest.mark.parametrize(
    ("client", "required", "forbidden"),
    [("codex", "codex exec", "claude"), ("claude", "claude -p", "codex exec")],
)
def test_reader_launch_accepts_only_the_installed_client(
    tmp_path: Path, machinery: str, client: str, required: str, forbidden: str,
):
    module = load_policy_module(
        machinery.replace("-", "_"), ROOT / "skills" / machinery / "client_model_policy.py")
    policy = tmp_path / "client-model-policy.json"
    policy.write_text(json.dumps({
        "schema_version": 1,
        "client": client,
        "required_runtime": required,
        "forbidden_runtime": forbidden,
        "fail_closed": True,
    }))

    assert module.validate_reader_command(required + " --model selected", policy)[:2] == required.split()
    with pytest.raises(ValueError, match="refuses reader command"):
        module.validate_reader_command(forbidden + " --model selected", policy)


@pytest.mark.parametrize(
    "machinery", ["implementation-machine", "description-machinery", "requirements-machine"],
)
def test_reader_launch_fails_closed_on_invalid_installed_policy(tmp_path: Path, machinery: str):
    module = load_policy_module(
        machinery.replace("-", "_"), ROOT / "skills" / machinery / "client_model_policy.py")
    policy = tmp_path / "client-model-policy.json"
    policy.write_text("{}")
    with pytest.raises(ValueError, match="invalid client model policy"):
        module.validate_reader_command("codex exec", policy)
