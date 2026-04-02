"""Tests for remote write and rebuild safety guards."""
from memory_knowledge.config import Settings
from memory_knowledge.guards import check_remote_write_guard


def _set_base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "pass")


def test_local_mode_allows_writes(monkeypatch):
    _set_base_env(monkeypatch)
    s = Settings()
    assert check_remote_write_guard(s, "test_tool") is None


def test_remote_mode_blocks_writes(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("DATA_MODE", "remote")
    s = Settings()
    result = check_remote_write_guard(s, "test_tool")
    assert result is not None
    assert result.status == "error"
    assert "ALLOW_REMOTE_WRITES" in result.error


def test_remote_mode_allows_writes_when_enabled(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("DATA_MODE", "remote")
    monkeypatch.setenv("ALLOW_REMOTE_WRITES", "true")
    s = Settings()
    assert check_remote_write_guard(s, "test_tool") is None


def test_remote_mode_blocks_destructive(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("DATA_MODE", "remote")
    monkeypatch.setenv("ALLOW_REMOTE_WRITES", "true")
    s = Settings()
    result = check_remote_write_guard(s, "test_tool", is_destructive=True)
    assert result is not None
    assert result.status == "error"
    assert "ALLOW_REMOTE_REBUILDS" in result.error


def test_remote_mode_allows_destructive_when_enabled(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("DATA_MODE", "remote")
    monkeypatch.setenv("ALLOW_REMOTE_WRITES", "true")
    monkeypatch.setenv("ALLOW_REMOTE_REBUILDS", "true")
    s = Settings()
    assert check_remote_write_guard(s, "test_tool", is_destructive=True) is None


def test_partial_remote_triggers_guard(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("PG_MODE", "remote")
    s = Settings()
    result = check_remote_write_guard(s, "test_tool")
    assert result is not None
    assert result.status == "error"


def test_guard_returns_correct_tool_name(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("DATA_MODE", "remote")
    s = Settings()
    result = check_remote_write_guard(s, "register_repository")
    assert result.tool_name == "register_repository"
