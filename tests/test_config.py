from memory_knowledge.config import Settings, get_settings, init_settings


def _set_base_env(monkeypatch):
    """Set required non-auth env vars."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "pass")


def test_settings_api_key_mode(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("AUTH_MODE", "api_key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    s = Settings()
    assert s.database_url == "postgresql://u:p@localhost/db"
    assert s.qdrant_url == "http://localhost:6333"
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.openai_api_key == "sk-test"
    assert s.auth_mode == "api_key"


def test_settings_codex_mode(monkeypatch):
    _set_base_env(monkeypatch)
    # codex is now the default — no need to set AUTH_MODE

    s = Settings()
    assert s.auth_mode == "codex"
    assert s.openai_api_key is None
    assert s.codex_auth_path == "~/.codex/auth.json"


def test_settings_defaults(monkeypatch):
    _set_base_env(monkeypatch)

    s = Settings()
    assert s.pg_pool_min_size == 5
    assert s.pg_pool_max_size == 20
    assert s.neo4j_max_pool_size == 50
    assert s.embedding_model == "text-embedding-3-small"
    assert s.embedding_dimensions == 1536
    assert s.server_port == 8000
    assert s.qdrant_api_key is None
    assert s.auth_mode == "codex"
    assert s.codex_auth_path == "~/.codex/auth.json"


def test_init_get_settings(monkeypatch):
    _set_base_env(monkeypatch)

    s = Settings()
    init_settings(s)
    assert get_settings() is s


# ── Data mode tests ──


def test_data_mode_defaults_to_local(monkeypatch):
    _set_base_env(monkeypatch)
    s = Settings()
    assert s.data_mode == "local"
    assert s.allow_remote_writes is False
    assert s.allow_remote_rebuilds is False
    assert s.is_any_remote() is False


def test_data_mode_remote(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("DATA_MODE", "remote")
    s = Settings()
    assert s.data_mode == "remote"
    assert s.is_any_remote() is True


def test_per_db_mode_override(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("PG_MODE", "remote")
    s = Settings()
    assert s.effective_mode("pg") == "remote"
    assert s.effective_mode("qdrant") == "local"
    assert s.effective_mode("neo4j") == "local"
    assert s.is_any_remote() is True


def test_all_local_not_remote(monkeypatch):
    _set_base_env(monkeypatch)
    s = Settings()
    assert s.effective_mode("pg") == "local"
    assert s.effective_mode("qdrant") == "local"
    assert s.effective_mode("neo4j") == "local"
    assert s.is_any_remote() is False
