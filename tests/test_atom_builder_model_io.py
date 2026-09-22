import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MODEL_IO = ROOT / "skills/atom-building-machinery/scripts/model_io.py"


def load_model_io():
    spec = importlib.util.spec_from_file_location("atom_builder_model_io", MODEL_IO)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bounded_model_call_uses_auth_only_codex_home_and_non_project_workspace(tmp_path, monkeypatch):
    model_io = load_model_io()
    auth = tmp_path / "source-auth.json"
    auth.write_text('{"token":"secret"}')
    monkeypatch.setattr(model_io, "AUTH_FILE", auth)
    observed = {}

    def completed(command, **kwargs):
        observed["codex_home"] = Path(kwargs["env"]["CODEX_HOME"])
        observed["workspace"] = Path(command[command.index("--cd") + 1])
        observed["home_entries"] = sorted(path.name for path in observed["codex_home"].iterdir())
        observed["auth_mode"] = (observed["codex_home"] / "auth.json").stat().st_mode & 0o777
        answer = Path(command[command.index("--output-last-message") + 1])
        answer.write_text('{"status":"generated"}')
        kwargs["stdout"].write(json.dumps({"type": "turn.completed"}) + "\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(model_io.subprocess, "run", completed)
    work = tmp_path / "call"
    assert model_io.invoke("bounded prompt", work) == '{"status":"generated"}'

    invocation = json.loads((work / "invocation.json").read_text())
    command = invocation["command"]
    assert "features.skip_host_skill_discovery=true" not in command
    assert "suppress_unstable_features_warning=true" in command
    assert "--ignore-rules" in command
    assert command.count("-c") == 5
    assert invocation["isolation"] == "temporary CODEX_HOME and non-project workspace; auth only"
    assert observed["home_entries"] == ["auth.json"]
    assert observed["auth_mode"] == 0o600
    assert work not in observed["workspace"].parents
    assert not observed["codex_home"].exists()
    assert not observed["workspace"].exists()
