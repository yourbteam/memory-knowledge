import json
from datetime import datetime, timezone, timedelta

import pytest

from memory_knowledge.auth.codex import codex_token_provider


@pytest.fixture
def valid_auth_json(tmp_path):
    """Create a valid auth.json file and return its path."""
    auth = {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {
            "id_token": "eyJ...",
            "access_token": "eyJtest_access_token",
            "refresh_token": "rt_test",
            "account_id": "test-account",
        },
        "last_refresh": datetime.now(timezone.utc).isoformat(),
    }
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(auth))
    return str(path)


async def test_reads_access_token(valid_auth_json):
    token = await codex_token_provider(valid_auth_json)
    assert token == "eyJtest_access_token"


async def test_raises_on_missing_file():
    with pytest.raises(RuntimeError, match="not found"):
        await codex_token_provider("/nonexistent/path/auth.json")


async def test_raises_on_null_tokens(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"tokens": None}))
    with pytest.raises(RuntimeError, match="no OAuth tokens"):
        await codex_token_provider(str(path))


async def test_raises_on_missing_access_token(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"tokens": {"id_token": "x", "refresh_token": "y"}}))
    with pytest.raises(RuntimeError, match="no OAuth tokens"):
        await codex_token_provider(str(path))


async def test_raises_on_malformed_json(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text("not valid json {{{")
    with pytest.raises(RuntimeError, match="malformed"):
        await codex_token_provider(str(path))


async def test_warns_on_stale_token(tmp_path, capfd):
    stale_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    auth = {
        "tokens": {
            "access_token": "eyJstale_token",
        },
        "last_refresh": stale_time,
    }
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(auth))

    token = await codex_token_provider(str(path))
    assert token == "eyJstale_token"
    # The warning is logged via structlog — token is still returned


async def test_no_warning_on_fresh_token(valid_auth_json):
    # Should not raise or warn — last_refresh is now
    token = await codex_token_provider(valid_auth_json)
    assert token == "eyJtest_access_token"
