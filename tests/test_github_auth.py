import json
from datetime import datetime, timedelta, timezone

import pytest

from memory_knowledge.auth import github_auth
from memory_knowledge.config import Settings


def _base_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "pass")
    monkeypatch.setenv("GITHUB_APP_CONFIG_PATH", str(tmp_path / "app-config.json"))
    return Settings(_env_file=None)


def test_build_auth_registry_from_config(monkeypatch, tmp_path):
    settings = _base_settings(monkeypatch, tmp_path)
    pem_path = tmp_path / "org.pem"
    pem_path.write_text("pem")
    config = [
        {
            "org": "thebteambg",
            "app_id": "123",
            "installation_id": "456",
            "pem_path": str(pem_path),
        }
    ]
    (tmp_path / "app-config.json").write_text(json.dumps(config))

    registry = github_auth.build_auth_registry(settings)
    assert registry.is_configured() is True
    assert registry.get("thebteambg") is not None
    assert registry.get("THEBTEAMBG") is not None


@pytest.mark.asyncio
async def test_get_authenticated_git_url_uses_github_app(monkeypatch, tmp_path):
    settings = _base_settings(monkeypatch, tmp_path)
    pem_path = tmp_path / "org.pem"
    pem_path.write_text("pem")
    config = [
        {
            "org": "thebteambg",
            "app_id": "123",
            "installation_id": "456",
            "pem_path": str(pem_path),
        }
    ]
    (tmp_path / "app-config.json").write_text(json.dumps(config))
    registry = github_auth.init_github_auth_registry(settings)
    auth = registry.get("thebteambg")

    async def fake_get_installation_token():
        return "ghs_token"

    monkeypatch.setattr(auth, "get_installation_token", fake_get_installation_token)

    url = await github_auth.get_authenticated_git_url(
        "https://github.com/thebteambg/FCSAPI.git",
        settings,
    )

    assert url == "https://x-access-token:ghs_token@github.com/thebteambg/FCSAPI.git"


@pytest.mark.asyncio
async def test_github_app_auth_caches_token(monkeypatch, tmp_path):
    pem_path = tmp_path / "app.pem"
    pem_path.write_text("pem")
    auth = github_auth.GitHubAppAuth(
        github_auth.GitHubAppSettings(
            github_app_id="123",
            github_app_installation_id="456",
            github_app_pem_path=str(pem_path),
            github_app_config_path=str(tmp_path / "config.json"),
        )
    )
    future_expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    monkeypatch.setattr(auth, "_generate_jwt", lambda: "jwt")

    calls = {"count": 0}

    async def fake_request(app_jwt):
        calls["count"] += 1
        return {"token": "ghs_shared", "expires_at": future_expiry}

    monkeypatch.setattr(auth, "_request_installation_token", fake_request)

    token1 = await auth.get_installation_token()
    token2 = await auth.get_installation_token()

    assert token1 == "ghs_shared"
    assert token2 == "ghs_shared"
    assert calls["count"] == 1
